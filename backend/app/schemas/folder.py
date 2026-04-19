from pydantic import BaseModel, Field
from typing import Optional


class CreateFolderRequest(BaseModel):
    dir: str
    folderName: str = Field(..., min_length=1, max_length=30, pattern=r'^[A-Za-z0-9\u4e00-\u9fa5\s\-_\.]+$')


class RenameFolderRequest(BaseModel):
    dir: str
    originName: str
    folderName: str = Field(..., min_length=1, max_length=30, pattern=r'^[A-Za-z0-9\u4e00-\u9fa5\s\-_\.]+$')


class FolderCreateResponse(BaseModel):
    date: str


class FolderRenameResponse(BaseModel):
    message: str


class FolderDeleteResponse(BaseModel):
    size: int
