# ⚡ FastAPI Tasks + Real-Time Chat

A Docker Compose project with a task-management API, Redis/Nginx caching, and a real-time, room-based chat service. Chat messages are broadcast live through Redis and streamed through Kafka to PostgreSQL for durable storage.

<p align="center">
  <strong>Tasks · Caching · WebSockets · Redis · Kafka · PostgreSQL</strong>
</p>

## ✨ What’s included

| Feature | What it does |
| --- | --- |
| **Task manager** | FastAPI endpoints for creating, viewing, updating, and deleting tasks. |
| **Layered caching** | Redis application caching and Nginx response caching for eligible GET requests. |
| **Live chat rooms** | A browser chat UI with room selection, display names, live WebSocket messaging, and reconnects. |
| **Message pipeline** | Redis handles live fan-out and recent room history; Kafka buffers messages for a background PostgreSQL writer. |
| **Developer tools** | Swagger API docs, Adminer, Kafka UI, and optional Locust load tests. |

## 🚀 Start the stack

### Requirements

- Docker Desktop with Docker Compose

No local Python installation is required. From the project directory, start all services:

```powershell
docker compose up --build -d
```

The first startup may take a little longer while Docker downloads images and Kafka initializes. Check the service status and logs with:

```powershell
docker compose ps
docker compose logs -f
```

### Open the apps

| App | URL |
| --- | --- |
| Task application / API | [http://localhost](http://localhost) |
| Task API documentation | [http://localhost/api/docs](http://localhost/api/docs) |
| Chat (default room) | [http://localhost:8001/chat](http://localhost:8001/chat) |
| Kafka UI | [http://localhost:8082](http://localhost:8082) |
| Adminer | [http://localhost:8080](http://localhost:8080) |
| Locust (when enabled) | [http://localhost:8089](http://localhost:8089) |

## 💬 Start a chat

Open the chat page and choose a room and display name in the URL:

```text
http://localhost:8001/chat?room=general&name=Alex
```

Change `room` to join or create another room, for example `design-team`. Room names can contain letters, numbers, underscores, and hyphens, up to 40 characters. Open the same room URL in another browser or tab to try live messaging. If `name` is omitted, the page asks for one.

The chat page loads the room’s recent messages, connects over WebSocket, and reconnects if the connection drops. Messages are limited to 2,000 characters, and Redis keeps up to 50 recent messages per room by default.

### Message flow

```text
Browser ──WebSocket──> Chat service ──> Redis Pub/Sub ──> Browsers in the room
                            │
                            └──> Kafka (chat.messages) ──> Chat writer ──> PostgreSQL
```

- **Redis** provides live room fan-out and recent history. It uses database 1, separate from the task cache in database 0.
- **Kafka** receives chat events asynchronously on the `chat.messages` topic.
- **Chat writer** consumes Kafka messages and inserts them into the PostgreSQL `chat_messages` table. Kafka offsets are committed after the database batch succeeds.
- **Kafka UI** is available at [http://localhost:8082](http://localhost:8082) for inspecting the local broker and topic.

Recent history shown in the chat is read from Redis; PostgreSQL stores the Kafka-consumed message records for durable storage.

## 🧪 Run Locust load tests

Start the application and Locust using the `loadtest` profile:

```powershell
docker compose --profile loadtest up --build -d
```

Open [http://localhost:8089](http://localhost:8089), set the number of users and spawn rate, and start the test. The Compose configuration runs `MixedUsers` against the application through Nginx by default.

Scenarios in `loadtest/locustfile.py`:

- `MixedUsers` — creates tasks and mixes list, item, and update requests.
- `ReadUsers` — reads task lists and existing task IDs.
- `ReadHeavyUsers` — primarily reads, with occasional writes and updates.
- `WriteUsers` — creates tasks.

To select another scenario, update the scenario name in the `locust` service command in `docker-compose.yml`, then recreate that service:

```powershell
docker compose --profile loadtest up -d --force-recreate locust
```

Locust writes task data to the database. Export statistics from the Locust UI, then compare a baseline and an after-change run:

```powershell
python loadtest/compare.py loadtest/results/nocache_stats.csv loadtest/results/cache_stats.csv
```

Change the paths to match where you saved the exported files.

## ⚙️ Cache configuration

| Variable | Default | Description |
| --- | --- | --- |
| `CACHE_ENABLED` | `true` | Set to `false` to bypass the Redis application cache. |
| `CACHE_TTL` | `30` | Redis application-cache entry lifetime in seconds. |

Disable the application cache in PowerShell:

```powershell
$env:CACHE_ENABLED = "false"
docker compose up --build -d
```

Restore the default in the same PowerShell window:

```powershell
Remove-Item Env:CACHE_ENABLED
```

View application cache counters at [http://localhost/api/cache/stats](http://localhost/api/cache/stats). API responses include an `X-Cache` header (`HIT`, `MISS`, or `BYPASS`); Nginx responses include `X-Cache-Status`.

## 🔌 Task API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/tasks?limit=100&offset=0` | List tasks, newest first. |
| `POST` | `/api/tasks` | Create a task with a title and optional description. |
| `GET` | `/api/tasks/{task_id}` | Get one task. |
| `PATCH` | `/api/tasks/{task_id}` | Update a task’s title, description, or completed state. |
| `DELETE` | `/api/tasks/{task_id}` | Delete a task. |
| `GET` | `/api/cache/stats` | View Redis application-cache statistics. |
| `GET` | `/api/health` | Check task API health. |

Chat endpoints are served by the chat service on port `8001`: `GET /health`, `GET /api/chat/{room}/history`, and `WS /ws/chat/{room}?name={name}`.

## 🧰 Services and ports

| Service | Purpose | Local address |
| --- | --- | --- |
| `nginx` | Task API reverse proxy and edge cache | [http://localhost](http://localhost) |
| `api` | Task FastAPI application | Proxied through Nginx |
| `chat` | Chat UI, WebSocket, and Redis integration | [http://localhost:8001](http://localhost:8001) |
| `db` | PostgreSQL for tasks and persisted chat messages | `localhost:5433` |
| `redis` | Task cache and chat history / Pub/Sub | Internal to the Compose network |
| `kafka` | Chat message broker | Internal to the Compose network |
| `chat_writer` | Kafka consumer that persists chat messages | Internal to the Compose network |
| `kafka-ui` | Kafka broker and topic UI | [http://localhost:8082](http://localhost:8082) |
| `adminer` | Database administration UI | [http://localhost:8080](http://localhost:8080) |
| `locust` | Optional load-testing UI | [http://localhost:8089](http://localhost:8089) |

## 🛑 Stop the services

```powershell
docker compose down
```

This stops and removes the containers but keeps named volumes and their data. To also remove the volumes and permanently delete their data, run:

```powershell
docker compose down -v
```
