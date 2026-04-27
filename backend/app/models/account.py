from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, SmallInteger, Boolean, TIMESTAMP
from .base import Base, BaseModel
from app.constants import StorageLimits, Identity, AccountDefaults


class Account(BaseModel):
    __tablename__ = "accounts"
    
    name = Column(String(128), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    signal_file_size = Column(BigInteger, default=StorageLimits.DEFAULT_SIGNAL_FILE_SIZE)
    total_file_size = Column(BigInteger, default=StorageLimits.DEFAULT_TOTAL_FILE_SIZE)
    used_size = Column(BigInteger, default=AccountDefaults.USED_SIZE, nullable=True)
    identity = Column(SmallInteger, default=Identity.USER)
    enable = Column(Boolean, default=AccountDefaults.ENABLE)
    email_verified_at = Column(TIMESTAMP, nullable=True)
    delete_date = Column(TIMESTAMP, nullable=True)
    last_sign_in_date = Column(TIMESTAMP, nullable=True)
