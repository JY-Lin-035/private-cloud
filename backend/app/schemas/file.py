from pydantic import BaseModel, Field
from typing import Optional


class FileUploadRequest(BaseModel):
    dir: str = Field(..., min_length=1, max_length=255)


class FileItem(BaseModel):
    type: str  # 'file' or 'folder'
    name: str
    size: str  # Human-readable size or '-'
    date: str  # ISO format datetime


class FileListResponse(BaseModel):
    file: list[FileItem]


class StorageInfoResponse(BaseModel):
    used_storage: int
    signal_storage: int
    total_storage: int


class FileUploadResponse(BaseModel):
    message: str


class FileDeleteResponse(BaseModel):
    size: int
