from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.constants import FileValidation


class FileUploadRequest(BaseModel):
    parent_folder_uuid: Optional[str] = None
    name: str


class DeleteFileRequest(BaseModel):
    file_uuid: str
    permanent: bool = False


class RestoreFileRequest(BaseModel):
    file_uuid: str


class FileResponse(BaseModel):
    uuid: str
    owner_id: int
    parent_folder_id: Optional[str]
    name: str
    size: int
    mime_type: Optional[str]
    storage_path: str
    shared: Optional[str]
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime]

    class Config:
        from_attributes = True


class FileItem(BaseModel):
    type: str  # 'file' or 'folder'
    uuid: str
    name: str
    size: int
    mime_type: Optional[str] = None
    date: datetime
    shared: Optional[str] = None


class FileListResponse(BaseModel):
    files: list[FileItem]


class StorageInfoResponse(BaseModel):
    used_storage: int
    signal_storage: int
    total_storage: int


class FileUploadResponse(BaseModel):
    uuid: str
    name: str
    size: int
    mime_type: str
    created_at: datetime


class FileDeleteResponse(BaseModel):
    uuid: str
    size: int
    permanent: bool


class FileRestoreResponse(BaseModel):
    uuid: str
    restored: bool
