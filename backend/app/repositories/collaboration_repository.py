from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.collaboration import Collaboration
from app.repositories.base_repository import BaseRepository


class CollaborationRepository(BaseRepository[Collaboration]):
    def __init__(self, db: Session):
        super().__init__(Collaboration, db)

    def get_by_file_uuid(self, file_uuid: str) -> List[Collaboration]:
        """Get all collaborations for a specific file."""
        stmt = select(Collaboration).where(Collaboration.file_uuid == file_uuid)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_owner(self, owner_id: int) -> List[Collaboration]:
        """Get all collaborations initiated by an owner (inviter)."""
        stmt = select(Collaboration).where(Collaboration.owner_id == owner_id)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_collaborator(self, collaborator_id: int) -> List[Collaboration]:
        """Get all collaborations where user is the collaborator (invitee)."""
        stmt = select(Collaboration).where(Collaboration.collaborator_id == collaborator_id)
        return list(self.db.execute(stmt).scalars().all())

    def get_by_file_and_collaborator(self, file_uuid: str, collaborator_id: int) -> Optional[Collaboration]:
        """Check if a specific collaboration exists."""
        stmt = select(Collaboration).where(
            Collaboration.file_uuid == file_uuid,
            Collaboration.collaborator_id == collaborator_id
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def remove_by_file_and_collaborator(self, file_uuid: str, collaborator_id: int) -> bool:
        """Remove a collaborator from a file."""
        collab = self.get_by_file_and_collaborator(file_uuid, collaborator_id)
        if collab:
            self.delete(collab)
            return True
        return False