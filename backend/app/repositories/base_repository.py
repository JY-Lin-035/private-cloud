from typing import TypeVar, Generic, Type, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, update, delete
from app.models.base import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], db: Session):
        self.model = model
        self.db = db
    
    def get_by_id(self, id: int) -> Optional[ModelType]:
        """Get a single record by ID."""
        stmt = select(self.model).where(self.model.id == id)
        return self.db.execute(stmt).scalar_one_or_none()
    
    def get_all(self) -> List[ModelType]:
        """Get all records."""
        stmt = select(self.model)
        return list(self.db.execute(stmt).scalars().all())
    
    def create(self, obj: ModelType) -> ModelType:
        """Create a new record."""
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj
    
    def update(self, obj: ModelType) -> ModelType:
        """Update a record."""
        self.db.commit()
        self.db.refresh(obj)
        return obj
    
    def delete(self, obj: ModelType) -> bool:
        """Delete a record."""
        self.db.delete(obj)
        self.db.commit()
        return True
    
    def delete_by_id(self, id: int) -> bool:
        """Delete a record by ID."""
        stmt = delete(self.model).where(self.model.id == id)
        self.db.execute(stmt)
        self.db.commit()
        return True
    
    def get_by_field(self, field_name: str, value: any) -> Optional[ModelType]:
        """Get a single record by a specific field."""
        stmt = select(self.model).where(getattr(self.model, field_name) == value)
        return self.db.execute(stmt).scalar_one_or_none()
    
    def exists_by_field(self, field_name: str, value: any) -> bool:
        """Check if a record exists with a specific field value."""
        stmt = select(self.model).where(getattr(self.model, field_name) == value)
        return self.db.execute(stmt).scalar_one_or_none() is not None
