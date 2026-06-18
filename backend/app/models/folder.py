from datetime import datetime
from sqlalchemy import Column, String, Integer, BigInteger, ForeignKey, TIMESTAMP, Boolean, Text, UniqueConstraint

from sqlalchemy.orm import relationship
from .base import Base, BaseModel
from app.constants import FolderValidation


class Folder(BaseModel):
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("uuid"),
        UniqueConstraint("shared", name="uq_folders_shared_non_null"),
    )

    uuid = Column(String(36), index=True,  nullable=False)
    owner_id = Column(
        Integer,
        ForeignKey('accounts.id', ondelete='CASCADE'),
        nullable=False,
        index=True
    )
    parent_id = Column(
        String(36),
        ForeignKey('folders.uuid', ondelete='CASCADE'),
        nullable=True,
        index=True
    )
    name = Column(
        String(FolderValidation.MAX_LENGTH),
        nullable=False
    )
    size = Column(BigInteger, default=0, nullable=False)
    shared = Column(String(100), nullable=True)
    deleted_at = Column(TIMESTAMP, nullable=True, index=True)
    is_system = Column(Boolean, default=False, nullable=False)  # System folders cannot be deleted
    limited_date = Column(TIMESTAMP, nullable=True)  # Expiration date for sharing
    available_user = Column(Text, nullable=True)  # JSON array of allowed user IDs

    # Relationships
    owner = relationship('Account', backref='folders')
    parent = relationship('Folder', remote_side=[uuid], backref='children')
