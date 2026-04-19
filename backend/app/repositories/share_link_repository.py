from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from app.models.share_link import ShareLink
from app.repositories.base_repository import BaseRepository


class ShareLinkRepository(BaseRepository[ShareLink]):
    def __init__(self, db: Session):
        super().__init__(ShareLink, db)
    
    def get_by_link(self, link: str) -> Optional[ShareLink]:
        """Get a share link by its link string."""
        return self.get_by_field('link', link)
    
    def get_by_owner(self, owner_id: int) -> List[ShareLink]:
        """Get all share links for a specific owner."""
        stmt = select(ShareLink).where(ShareLink.owner_id == owner_id)
        return list(self.db.execute(stmt).scalars().all())
    
    def get_by_owner_and_path(self, owner_id: int, path: str, file_name: str) -> Optional[ShareLink]:
        """Get a share link by owner, path, and filename."""
        stmt = select(ShareLink).where(
            and_(
                ShareLink.owner_id == owner_id,
                ShareLink.path == path,
                ShareLink.file_name == file_name
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()
    
    def delete_by_owner_and_path(self, owner_id: int, path: str, file_name: str) -> bool:
        """Delete a share link by owner, path, and filename."""
        stmt = select(ShareLink).where(
            and_(
                ShareLink.owner_id == owner_id,
                ShareLink.path == path,
                ShareLink.file_name == file_name
            )
        )
        link = self.db.execute(stmt).scalar_one_or_none()
        if link:
            return self.delete(link)
        return False
    
    def delete_by_link(self, link: str) -> bool:
        """Delete a share link by its link string."""
        link = self.get_by_link(link)
        if link:
            return self.delete(link)
        return False
