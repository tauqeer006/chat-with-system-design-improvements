"""Reads chat messages from Kafka and saves them to Postgres in batches."""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("writer")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "kafka:9092")
TOPIC = os.getenv("KAFKA_TOPIC", "chat.messages")
DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(DATABASE_URL, pool_size=5, pool_pre_ping=True)


def init_db():
    with engine.begin() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            room TEXT NOT NULL,
            name TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL)"""))
        c.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_room_time "
                       "ON chat_messages (room, created_at DESC)"))


def insert_batch(rows):
    with engine.begin() as c:                      # one transaction per batch
        c.execute(text(
            "INSERT INTO chat_messages (id, room, name, text, created_at) "
            "VALUES (:id, :room, :name, :text, :created_at) "
            "ON CONFLICT (id) DO NOTHING"), rows)  # a re-delivered message is ignored


async def main():
    await asyncio.to_thread(init_db)
    consumer = AIOKafkaConsumer(
        TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="chat-db-writer",
        enable_auto_commit=False,                  # we commit only after Postgres succeeded
        auto_offset_reset="earliest",
    )
    await consumer.start()
    log.info("writer started")
    try:
        while True:
            batches = await consumer.getmany(timeout_ms=1000, max_records=500)
            rows = []
            for msgs in batches.values():
                for m in msgs:
                    e = json.loads(m.value)
                    rows.append({
                        "id": e["id"], "room": e["room"], "name": e["name"],
                        "text": e["text"],
                        "created_at": datetime.fromtimestamp(e["ts"], tz=timezone.utc),
                    })
            if not rows:
                continue
            while True:                            # retry until Postgres accepts the batch
                try:
                    await asyncio.to_thread(insert_batch, rows)
                    break
                except Exception as exc:
                    log.warning("DB insert failed, retrying: %s", exc)
                    await asyncio.sleep(2)
            await consumer.commit()                # only now is the batch "done"
            log.info("saved %d messages", len(rows))
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())