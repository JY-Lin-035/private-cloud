from sqlalchemy import Column, String, Integer, Boolean, TIMESTAMP, Index
from .base import BaseModel


class IpControl(BaseModel):
    __tablename__ = "ip_control"

    subject_type = Column(String(16), nullable=False)   # ip | ip_token | user
    ip = Column(String(45), nullable=True)
    token = Column(String(64), nullable=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(128), nullable=True)
    action = Column(String(8), nullable=False, default="slow")       # slow | block
    scope = Column(String(16), nullable=False, default="transfer")   # transfer | full
    direction = Column(String(8), nullable=False, default="both")    # up | down | both
    delay_ms = Column(Integer, nullable=False, default=2000)
    upload_kbps = Column(Integer, nullable=True)
    download_kbps = Column(Integer, nullable=True)
    reason = Column(String(255), nullable=True)
    auto = Column(Boolean, nullable=False, default=False)
    created_by = Column(Integer, nullable=True)
    expires_at = Column(TIMESTAMP, nullable=True)

    __table_args__ = (
        Index("ix_ip_control_ip", "ip"),
        Index("ix_ip_control_user", "user_id"),
    )
