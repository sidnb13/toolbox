from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ApiKey(Base):
    __tablename__ = "api_keys"

    key = Column(String, primary_key=True)
    instance_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class ShutdownResponse(str, Enum):
    ACCEPT = "accept"
    DENY = "deny"
    PENDING = "pending"


class ShutdownRequest:
    def __init__(self, instance_id: str, message_id: str, platform: str):
        self.instance_id = instance_id
        self.message_id = message_id  # Slack ts or Discord message id
        self.platform = platform  # "slack" or "discord"
        self.start_time = datetime.now()
        self.response = ShutdownResponse.PENDING
        self.responder: Optional[str] = None
