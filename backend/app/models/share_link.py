from sqlalchemy import Column, String, Integer, ForeignKey
from .base import Base, BaseModel


class ShareLink(BaseModel):
    __tablename__ = "share_links"
    
    path = Column(String(255), nullable=False)
    file_name = Column(String(255), nullable=True)
    link = Column(String(255), unique=True, nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey('accounts.id', ondelete='CASCADE'), nullable=False)
