from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from .base import Base, BaseModel


class Collaboration(BaseModel):
    __tablename__ = "collaborations"
    __table_args__ = (
        UniqueConstraint("file_uuid", "collaborator_id", name="uq_collab_file_user"),
    )

    file_uuid = Column(
        String(36),
        ForeignKey("files.uuid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id = Column(
        Integer,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collaborator_id = Column(
        Integer,
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    permission = Column(String(20), nullable=False, server_default="editor")

    # Relationships
    file = relationship("File", backref="collaborations")
    owner = relationship("Account", foreign_keys=[owner_id], backref="owned_collaborations")
    collaborator = relationship("Account", foreign_keys=[collaborator_id], backref="collaborations")