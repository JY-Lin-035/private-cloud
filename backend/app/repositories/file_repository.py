import uuid
import secrets
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from app.models.file import File
from app.repositories.base_repository import BaseRepository


class FileRepository(BaseRepository[File]):
    def __init__(self, db: Session):
        super().__init__(File, db)
    
    def get_by_uuid(self, file_uuid: str) -> Optional[File]:
        """Get a file by UUID."""
        return self.get_by_field('uuid', file_uuid)
    
    def get_by_owner(self, owner_id: int) -> List[File]:
        """Get all files by owner ID."""
        stmt = select(File).where(
            and_(
                File.owner_id == owner_id,
                File.deleted_at.is_(None)
            )
        )
        return list(self.db.execute(stmt).scalars().all())
    
    def get_by_folder(self, folder_uuid: str) -> List[File]:
        """Get all files by folder UUID."""
        stmt = select(File).where(
            and_(
                File.parent_folder_id == folder_uuid,
                File.deleted_at.is_(None)
            )
        )
        return list(self.db.execute(stmt).scalars().all())
    
    def get_trash_by_owner(self, owner_id: int) -> List[File]:
        """Get soft-deleted files by owner ID."""
        stmt = select(File).where(
            and_(
                File.owner_id == owner_id,
                File.deleted_at.isnot(None)
            )
        )
        return list(self.db.execute(stmt).scalars().all())
    
    def uuid_exists(self, file_uuid: str) -> bool:
        """Check if UUID exists."""
        return self.exists_by_field('uuid', file_uuid)
    
    def shared_exists(self, shared_hash: str) -> bool:
        """Check if share hash exists."""
        stmt = select(File).where(
            and_(
                File.shared == shared_hash,
                File.deleted_at.is_(None)
            )
        )
        return self.db.execute(stmt).scalar_one_or_none() is not None
    
    def create_with_uuid_retry(self, obj: File, max_retries: int = 3) -> File:
        """Create file with UUID collision retry logic."""
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
    
    def generate_share_hash(self, file_uuid: str, max_retries: int = 3) -> str:
        """Generate share hash with collision retry logic."""
        for attempt in range(max_retries):
            share_hash = secrets.token_urlsafe(32)
            
            if not self.shared_exists(share_hash):
                file = self.get_by_uuid(file_uuid)
                if file:
                    file.shared = share_hash
                    try:
                        self.db.commit()
                        self.db.refresh(file)
                        return share_hash
                    except IntegrityError:
                        self.db.rollback()
                        if attempt == max_retries - 1:
                            raise
                        continue
        
        raise RuntimeError("Failed to generate unique share hash after retries")
    
    def soft_delete(self, file_uuid: str) -> bool:
        """Soft delete a file by UUID."""
        from datetime import datetime
        file = self.get_by_uuid(file_uuid)
        if file:
            file.deleted_at = datetime.utcnow()
            self.db.commit()
            return True
        return False
    
    def restore(self, file_uuid: str) -> bool:
        """Restore a soft-deleted file by UUID."""
        file = self.db.execute(
            select(File).where(File.uuid == file_uuid)
        ).scalar_one_or_none()
        
        if file and file.deleted_at:
            file.deleted_at = None
            self.db.commit()
            return True
        return False
    
    def hard_delete(self, file_uuid: str) -> bool:
        """Hard delete a file by UUID."""
        stmt = select(File).where(File.uuid == file_uuid)
        file = self.db.execute(stmt).scalar_one_or_none()
        if file:
            self.db.delete(file)
            self.db.commit()
            return True
        return False
    
    def get_by_share_hash(self, share_hash: str) -> Optional[File]:
        """Get a file by share hash."""
        stmt = select(File).where(
            and_(
                File.shared == share_hash,
                File.deleted_at.is_(None)
            )
        )
        return self.db.execute(stmt).scalar_one_or_none()
