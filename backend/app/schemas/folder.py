from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from app.constants import FolderValidation
from app.utils.name_validation import validate_display_name


def _checked_name(value: str) -> str:
    cleaned, error = validate_display_name(value)
    if error:
        raise ValueError(error)
    return cleaned


class CreateFolderRequest(BaseModel):
    parent_folder_uuid: Optional[str] = None
    name: str = Field(..., min_length=FolderValidation.MIN_LENGTH, max_length=FolderValidation.MAX_LENGTH)

    @field_validator('name')
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _checked_name(v)


class RenameFolderRequest(BaseModel):
    folder_uuid: str
    name: str = Field(..., min_length=FolderValidation.MIN_LENGTH, max_length=FolderValidation.MAX_LENGTH)

    @field_validator('name')
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return _checked_name(v)


class DeleteFolderRequest(BaseModel):
    folder_uuid: str
    permanent: bool = False


class RestoreFolderRequest(BaseModel):
    folder_uuid: str


class FolderResponse(BaseModel):
    uuid: str
    owner_id: int
    parent_id: Optional[str]
    name: str
    size: int
    shared: Optional[str]
    limited_date: Optional[datetime] = None
    available_user: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]

    class Config:
        from_attributes = True


class FolderTreeResponse(BaseModel):
    uuid: str
    name: str
    size: int
    shared: Optional[str]
    children: list['FolderTreeResponse'] = []

    class Config:
        from_attributes = True


class FolderCreateResponse(BaseModel):
    uuid: str
    name: str
    created_at: datetime


class FolderRenameResponse(BaseModel):
    uuid: str
    name: str
    updated_at: datetime


class FolderDeleteResponse(BaseModel):
    uuid: str
    size: int
    permanent: bool


class FolderRestoreResponse(BaseModel):
    uuid: str
    restored: bool
