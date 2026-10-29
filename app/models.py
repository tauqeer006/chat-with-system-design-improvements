from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from .database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(String(1000), default="")
    done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
