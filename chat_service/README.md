# Real-time chat service

The chat service is part of the project’s Docker Compose stack. It serves a browser-based room chat, uses Redis for live message fan-out and recent history, and publishes chat events to Kafka for asynchronous PostgreSQL persistence.

For the full project setup, task API, caching, load-test instructions, and service overview, see the [project README](../README.md).

## Run

From the project directory:

```powershell
docker compose up --build -d chat
```

Compose also starts the required Redis and Kafka services. The Kafka consumer (`chat_writer`) is part of the full stack; start everything to run the complete persistence pipeline:

```powershell
docker compose up --build -d
```

Open [http://localhost:8001/chat](http://localhost:8001/chat). To enter a room with a chosen display name, use a URL such as:

```text
http://localhost:8001/chat?room=general&name=Alex
```

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/chat` | Browser chat UI. |
| `GET` | `/health` | Chat service and Redis status. |
| `GET` | `/api/chat/{room}/history` | Recent room messages from Redis. |
| `WS` | `/ws/chat/{room}?name={name}` | Live room messaging. |

Messages are published to the Kafka topic `chat.messages`. The `chat_writer` service consumes that topic and inserts messages into the PostgreSQL `chat_messages` table.
