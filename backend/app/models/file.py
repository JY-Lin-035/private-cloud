from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, ForeignKey, TIMESTAMP, Text, UniqueConstraint

from sqlalchemy.orm import relationship
from .base import Base, BaseModel
from app.constants import FileValidation


class File(BaseModel):
    __tablename__ = "files"
    __table_args__ = (
        UniqueConstraint("uuid"),
        UniqueConstraint("shared", name="uq_files_shared_non_null"),
    )

    uuid = Column(String(36), index=True, nullable=False)
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
    shared = Column(String(100), nullable=True)
    deleted_at = Column(TIMESTAMP, nullable=True, index=True)
    limited_date = Column(TIMESTAMP, nullable=True)  # Expiration date for sharing
    available_user = Column(Text, nullable=True)  # JSON array of allowed user IDs

    # Relationships
    owner = relationship('Account', backref='files')
    parent_folder = relationship('Folder', backref='files')
