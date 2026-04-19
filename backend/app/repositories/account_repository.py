from typing import Optional
from sqlalchemy.orm import Session
from app.models.account import Account
from app.repositories.base_repository import BaseRepository


class AccountRepository(BaseRepository[Account]):
    def __init__(self, db: Session):
        super().__init__(Account, db)
    
    def get_by_name(self, name: str) -> Optional[Account]:
        """Get an account by username."""
        return self.get_by_field('name', name)
    
    def get_by_email(self, email: str) -> Optional[Account]:
        """Get an account by email."""
        return self.get_by_field('email', email)
    
    def name_exists(self, name: str) -> bool:
        """Check if username exists."""
        return self.exists_by_field('name', name)
    
    def email_exists(self, email: str) -> bool:
        """Check if email exists."""
        return self.exists_by_field('email', email)
