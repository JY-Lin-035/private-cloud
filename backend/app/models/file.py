from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from .base import Base, BaseModel
from app.constants import FileValidation


class File(BaseModel):
    __tablename__ = "files"

    uuid = Column(String(36), primary_key=True, unique=True, index=True, nullable=False)
    owner_id = Column(
        Integer,
        ForeignKey('accounts.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    parent_folder_id = Column(
        String(36),
        ForeignKey('folders.uuid', ondelete='CASCADE'),
        nullable=True,
        index=True
    )
    name = Column(String(255), nullable=False)
    size = Column(BigInteger, default=0, nullable=False)
    mime_type = Column(String(100), nullable=True)
    storage_path = Column(String(512), nullable=False)
    shared = Column(String(100), nullable=True, unique=True, index=True)
    deleted_at = Column(TIMESTAMP, nullable=True, index=True)

    # Relationships
    owner = relationship('Account', backref='files')
    parent_folder = relationship('Folder', backref='files')
