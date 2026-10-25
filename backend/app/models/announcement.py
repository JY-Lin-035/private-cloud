from sqlalchemy import Column, String, Boolean, TIMESTAMP
from .base import BaseModel


class Announcement(BaseModel):
    __tablename__ = "announcements"

    content = Column(String(500), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    expires_at = Column(TIMESTAMP, nullable=True)  # naive UTC; NULL = indefinite
