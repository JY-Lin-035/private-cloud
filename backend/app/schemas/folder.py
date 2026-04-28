from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.constants import FolderValidation


class CreateFolderRequest(BaseModel):
    parent_folder_uuid: Optional[str] = None
    name: str = Field(..., min_length=FolderValidation.MIN_LENGTH, max_length=FolderValidation.MAX_LENGTH, pattern=FolderValidation.PATTERN)


class RenameFolderRequest(BaseModel):
    folder_uuid: str
    name: str = Field(..., min_length=FolderValidation.MIN_LENGTH, max_length=FolderValidation.MAX_LENGTH, pattern=FolderValidation.PATTERN)


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
