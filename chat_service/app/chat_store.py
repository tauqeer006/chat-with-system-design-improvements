"""Redis helpers for the chat service (same style as the task API's cache.py).

- History : Redis list  chat:<room>:history   (newest first, capped)
- Live    : Redis pub/sub channel chat:<room> (every worker subscribes, so it
            works with any number of workers or containers)
Uses Redis DB 1 by default so keys never mix with the task cache in DB 0.
Everything fails open: if Redis is down, history is empty and posting is dropped
instead of crashing the app.
"""
import json
import os
import time

import redis.asyncio as aioredis
from redis.exceptions import RedisError


import logging
import uuid
from aiokafka import AIOKafkaProducer

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/1")
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "50"))
HISTORY_TTL = int(os.getenv("HISTORY_TTL", str(7 * 24 * 3600)))  # drop idle rooms after 7 days
MAX_LEN = int(os.getenv("MAX_MESSAGE_LEN", "2000"))

# No socket_timeout: pub/sub connections sit idle waiting for messages.
r = aioredis.from_url(
    REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=1,
    health_check_interval=30,
)


log = logging.getLogger("chat")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "chat.messages")
producer: AIOKafkaProducer | None = None


def channel(room: str) -> str:
    return f"chat:{room}"


def history_key(room: str) -> str:
    return f"chat:{room}:history"


async def history(room: str) -> list[dict]:
    try:
        items = await r.lrange(history_key(room), 0, HISTORY_LIMIT - 1)
    except RedisError:
        return []
    return [json.loads(i) for i in reversed(items)]      # oldest first


async def post(room: str, name: str, text: str) -> bool:
    event = json.dumps({
    "id": uuid.uuid4().hex,
    "room": room,                # add this line
    "name": name,
    "text": text,
    "ts": time.time()})
    try:
        pipe = r.pipeline(transaction=False)
        pipe.lpush(history_key(room), event)
        pipe.ltrim(history_key(room), 0, HISTORY_LIMIT - 1)
        pipe.expire(history_key(room), HISTORY_TTL)
        pipe.publish(channel(room), event)               # fan-out to all workers
        await pipe.execute()

    except RedisError:
        return False

    if producer:                                   # hand over to Kafka, don't wait for Postgres
        try:
            await producer.send(TOPIC, event.encode(), key=room.encode())
        except Exception as exc:
            log.warning("Kafka send failed: %s", exc)
    return True

async def stats() -> dict:
    try:
        rooms = [k async for k in r.scan_iter(match="chat:*:history", count=100)]
        return {"redis": "ok", "rooms_with_history": len(rooms)}
    except RedisError:
        return {"redis": "down"}



async def start_producer():
    global producer
    try:
        p = AIOKafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP, linger_ms=20)
        await p.start()
        producer = p
    except Exception as exc:                       # fail open, like the Redis helpers
        log.warning("Kafka unavailable, messages will not be persisted: %s", exc)


async def stop_producer():
    if producer:
        await producer.stop()
