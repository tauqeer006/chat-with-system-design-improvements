import time
from contextlib import asynccontextmanager
from pathlib import Path
import hashlib
import re

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import TypeAdapter

from . import cache, models, schemas
from .database import Base, SessionLocal, engine, wait_for_db
from fastapi.responses import FileResponse, HTMLResponse


STATIC_DIR = Path(__file__).parent / "static"
LIST_ADAPTER = TypeAdapter(list[schemas.TaskOut])

ASSET_RE = re.compile(r'(/static/([^"\'?]+\.(?:js|css)))')


def _version(rel: str) -> str:
    return hashlib.md5((STATIC_DIR / rel).read_bytes()).hexdigest()[:10]


def render_index() -> str:
    """Rewrite /static/app.js -> /static/app.js?v=<content hash>."""
    html = (STATIC_DIR / "index.html").read_text()
    return ASSET_RE.sub(lambda m: f"{m.group(1)}?v={_version(m.group(2))}", html)


INDEX_HTML = render_index()   # computed once at startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_for_db()
    try:
        Base.metadata.create_all(bind=engine)  # creates the tables on first run
    except Exception as exc:  # several workers can race on a fresh DB; the table then exists
        print(f"create_all skipped: {exc}")
    yield


app = FastAPI(title="Task API", lifespan=lifespan)


class ProcessTimeMiddleware:
    """Adds X-Process-Time (ms) to every response (plain ASGI: cheap under load)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                elapsed = (time.perf_counter() - start) * 1000
                headers = list(message.get("headers", []))
                headers.append((b"x-process-time", f"{elapsed:.2f}".encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_header)


app.add_middleware(ProcessTimeMiddleware)


def json_response(payload: bytes, state: str) -> Response:
    """Return already-serialized JSON. X-Cache: HIT | MISS | BYPASS (cache disabled)."""
    return Response(payload, media_type="application/json", headers={"X-Cache": state})


@app.get("/", include_in_schema=False)
def index():
    return HTMLResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/cache/stats")
def cache_stats():
    """Hit/miss counters and Redis memory: use this to monitor the cache."""
    return cache.stats()


# ---------------------------------------------------------------- WRITES
# Writes are NOT cached. They hit the DB, then invalidate the affected cache entries.


@app.post("/api/tasks", response_model=schemas.TaskOut, status_code=201)
def create_task(payload: schemas.TaskCreate):
    with SessionLocal() as db:
        task = models.Task(**payload.model_dump())
        db.add(task)
        db.commit()
        db.refresh(task)
    cache.invalidate()                      # CACHE: list pages are stale now
    return task


@app.patch("/api/tasks/{task_id}", response_model=schemas.TaskOut)
def update_task(task_id: int, payload: schemas.TaskUpdate):
    with SessionLocal() as db:
        task = db.get(models.Task, task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(task, key, value)
        db.commit()
        db.refresh(task)
    cache.invalidate(task_id)               # CACHE: drop this item + stale list pages
    return task


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    with SessionLocal() as db:
        task = db.get(models.Task, task_id)
        if not task:
            raise HTTPException(404, "Task not found")
        db.delete(task)
        db.commit()
    cache.invalidate(task_id)               # CACHE: drop this item + stale list pages


# ---------------------------------------------------------------- READS (cached)


@app.get("/api/tasks", response_model=list[schemas.TaskOut])
def list_tasks(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    key = None
    if cache.CACHE_ENABLED:
        key = cache.list_key(limit, offset)             # CACHE: 1) look in Redis first
        cached = cache.get(key)
        if cached is not None:
            cache.record("list_hit")
            return json_response(cached, "HIT")

    with SessionLocal() as db:                          # 2) miss -> query the DB
        rows = (
            db.query(models.Task)
            .order_by(models.Task.id.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )
    payload = LIST_ADAPTER.dump_json(LIST_ADAPTER.validate_python(rows, from_attributes=True))

    if key:
        cache.put(key, payload)                         # 3) store for next time (TTL)
        cache.record("list_miss")
        return json_response(payload, "MISS")
    return json_response(payload, "BYPASS")


@app.get("/api/tasks/{task_id}", response_model=schemas.TaskOut)
def get_task(task_id: int):
    key = cache.item_key(task_id)
    if cache.CACHE_ENABLED:
        cached = cache.get(key)                         # CACHE: 1) look in Redis first
        if cached is not None:
            cache.record("item_hit")
            return json_response(cached, "HIT")

    with SessionLocal() as db:                          # 2) miss -> query the DB
        task = db.get(models.Task, task_id)
        if not task:
            raise HTTPException(404, "Task not found")  # 404s are never cached
    payload = schemas.TaskOut.model_validate(task).model_dump_json().encode()

    if cache.CACHE_ENABLED:
        cache.put(key, payload)                         # 3) store for next time (TTL)
        cache.record("item_miss")
        return json_response(payload, "MISS")
    return json_response(payload, "BYPASS")

class CachedStatic(StaticFiles):
    """Adds Cache-Control to static files so Nginx (and later a real CDN) can cache them."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            if scope.get("query_string", b"").startswith(b"v="):
                # versioned URL: content for this exact URL never changes
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                # unversioned URL: short TTL, then revalidate with the ETag
                response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=60"
        return response


app.mount("/static", CachedStatic(directory=STATIC_DIR), name="static")