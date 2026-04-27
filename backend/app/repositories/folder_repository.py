import uuid
import secrets
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from app.models.folder import Folder
from app.repositories.base_repository import BaseRepository


class FolderRepository(BaseRepository[Folder]):
    def __init__(self, db: Session):
        super().__init__(Folder, db)
    
    def get_by_uuid(self, folder_uuid: str) -> Optional[Folder]:
        """Get a folder by UUID."""
        return self.get_by_field('uuid', folder_uuid)
    
    def get_by_owner(self, owner_id: int) -> List[Folder]:
        """Get all folders by owner ID."""
        stmt = select(Folder).where(
            and_(
                Folder.owner_id == owner_id,
                Folder.deleted_at.is_(None)
            )
        )
        return list(self.db.execute(stmt).scalars().all())
    
    def get_home_folder(self, owner_id: int) -> Optional[Folder]:
        """Get the Home folder for a user."""
        stmt = select(Folder).where(
            and_(
                Folder.owner_id == owner_id,
                Folder.name == 'Home',
                Folder.is_system == True,
                Folder.deleted_at.is_(None)
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()
    
    def get_folder_path(self, folder_uuid: str) -> List[Dict[str, str]]:
        """Get the full path from root to the current folder."""
        path = []
        current = self.get_by_uuid(folder_uuid)
        
        while current:
            path.insert(0, {"uuid": current.uuid, "name": current.name})
            if current.parent_id:
                current = self.get_by_uuid(current.parent_id)
            else:
                break
        
        return path
    
    def get_by_parent(self, parent_uuid: str) -> List[Folder]:
        """Get all folders by parent UUID."""
        stmt = select(Folder).where(
            and_(
                Folder.parent_id == parent_uuid,
                Folder.deleted_at.is_(None)
            )
        )
        return list(self.db.execute(stmt).scalars().all())
    
    def get_trash_by_owner(self, owner_id: int) -> List[Folder]:
        """Get soft-deleted folders by owner ID."""
        stmt = select(Folder).where(
            and_(
                Folder.owner_id == owner_id,
                Folder.deleted_at.isnot(None)
            )
        )
        return list(self.db.execute(stmt).scalars().all())
    
    def uuid_exists(self, folder_uuid: str) -> bool:
        """Check if UUID exists."""
        return self.exists_by_field('uuid', folder_uuid)
    
    def shared_exists(self, shared_hash: str) -> bool:
        """Check if share hash exists."""
        stmt = select(Folder).where(
            and_(
                Folder.shared == shared_hash,
                Folder.deleted_at.is_(None)
            )
        )
        return self.db.execute(stmt).scalar_one_or_none() is not None
    
    def create_with_uuid_retry(self, obj: Folder, max_retries: int = 3) -> Folder:
        """Create folder with UUID collision retry logic."""
        for attempt in range(max_retries):
            if obj.uuid is None:
                obj.uuid = str(uuid.uuid4())
            
            try:
                self.db.add(obj)
                self.db.commit()
                self.db.refresh(obj)
                return obj
            except IntegrityError:
                self.db.rollback()
                if attempt == max_retries - 1:
                    raise
                obj.uuid = str(uuid.uuid4())
        
        raise RuntimeError("Failed to generate unique UUID after retries")
    
    def generate_share_hash(self, folder_uuid: str, max_retries: int = 3) -> str:
        """Generate share hash with collision retry logic."""
        for attempt in range(max_retries):
            share_hash = secrets.token_urlsafe(32)
            
            if not self.shared_exists(share_hash):
                folder = self.get_by_uuid(folder_uuid)
                if folder:
                    folder.shared = share_hash
                    try:
                        self.db.commit()
                        self.db.refresh(folder)
                        return share_hash
                    except IntegrityError:
                        self.db.rollback()
                        if attempt == max_retries - 1:
                            raise
                        continue
        
        raise RuntimeError("Failed to generate unique share hash after retries")
    
    def soft_delete(self, folder_uuid: str) -> bool:
        """Soft delete a folder by UUID."""
        from datetime import datetime
        folder = self.get_by_uuid(folder_uuid)
        if folder:
            folder.deleted_at = datetime.utcnow()
            self.db.commit()
            return True
        return False
    
    def restore(self, folder_uuid: str) -> bool:
        """Restore a soft-deleted folder by UUID."""
        folder = self.db.execute(
            select(Folder).where(Folder.uuid == folder_uuid)
        ).scalar_one_or_none()
        
        if folder and folder.deleted_at:
            folder.deleted_at = None
            self.db.commit()
            return True
        return False
    
    def hard_delete(self, folder_uuid: str) -> bool:
        """Hard delete a folder by UUID."""
        stmt = select(Folder).where(Folder.uuid == folder_uuid)
        folder = self.db.execute(stmt).scalar_one_or_none()
        if folder:
            self.db.delete(folder)
            self.db.commit()
            return True
        return False
