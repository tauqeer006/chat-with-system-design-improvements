import asyncio
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse
from redis.exceptions import RedisError

from . import chat_store as store

STATIC_DIR = Path(__file__).parent / "static"
CHAT_HTML = (STATIC_DIR / "chat.html").read_text()
ROOM_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")   # keeps Redis keys clean

@asynccontextmanager
async def lifespan(app: FastAPI):
    await store.start_producer()
    yield
    await store.stop_producer()
    await store.r.aclose()


app = FastAPI(title="Chat Service", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/chat")


@app.get("/chat", include_in_schema=False)
def chat_page():
    return HTMLResponse(CHAT_HTML, headers={"Cache-Control": "no-cache"})


@app.get("/health")
async def health():
    return {"status": "ok", **await store.stats()}


@app.get("/api/chat/{room}/history")
async def chat_history(room: str):
    if not ROOM_RE.match(room):
        return []
    return await store.history(room)


@app.websocket("/ws/chat/{room}")
async def chat_ws(ws: WebSocket, room: str, name: str = "Anonymous"):
    if not ROOM_RE.match(room):
        await ws.close(code=1008)
        return
        print("Room found: %s", room , "Name found: %s", name)
    await ws.accept()
    name = name.strip()[:30] or "Anonymous"

    pubsub = store.r.pubsub()
    print("Subscribing to room: %s", room)
    try:
        await pubsub.subscribe(store.channel(room))
    except RedisError:
        await ws.close(code=1011)
        return

    async def to_browser():
        # Redis -> this browser (everyone's messages, including mine)
        async for msg in pubsub.listen():
            if msg["type"] == "message":
                await ws.send_text(msg["data"])

    async def from_browser():
        # this browser -> Redis
        while True:
            text = (await ws.receive_text()).strip()[: store.MAX_LEN]
            if text:
                await store.post(room, name, text)

    tasks = [asyncio.create_task(to_browser()), asyncio.create_task(from_browser())]
    try:
        # when either side ends (browser closed / Redis dropped), stop both
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()
        try:
            await pubsub.unsubscribe(store.channel(room))
            await pubsub.aclose()
        except RedisError:
            pass
