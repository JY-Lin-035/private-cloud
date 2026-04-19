from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, SmallInteger, Boolean, TIMESTAMP
from .base import Base, BaseModel


class Account(BaseModel):
    __tablename__ = "accounts"
    
    name = Column(String(128), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    signal_file_size = Column(BigInteger, default=524288000)  # Default 500MB
    total_file_size = Column(BigInteger, default=10737418240)  # Default 10GB
    used_size = Column(BigInteger, default=0, nullable=True)
    identity = Column(SmallInteger, default=0)  # 0: User, 1: Admin
    enable = Column(Boolean, default=False)
    email_verified_at = Column(TIMESTAMP, nullable=True)
    delete_date = Column(TIMESTAMP, nullable=True)
    last_sign_in_date = Column(TIMESTAMP, nullable=True)
    remember_token = Column(String(100), nullable=True)
