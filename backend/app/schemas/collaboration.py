from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class CollaborationAddRequest(BaseModel):
    file_uuid: str
    collaborator_name: str
    collaborator_email: str


class CollaborationRemoveRequest(BaseModel):
    file_uuid: str
    collaborator_id: int


class CollaborationItem(BaseModel):
    """邀請者看到的成員清單"""
    id: int
    file_uuid: str
    file_name: str
    collaborator_id: int
    collaborator_name: str
    collaborator_email: str
    permission: str
    created_at: datetime

    class Config:
        from_attributes = True


class MyCollaborationItem(BaseModel):
    """被邀請者看到的共編檔案清單"""
    id: int
    file_uuid: str
    file_name: str
    owner_id: int
    owner_name: str
    owner_email: str
    permission: str
    created_at: datetime

    class Config:
        from_attributes = True


class CollaborationListResponse(BaseModel):
    items: List[CollaborationItem]
    total: int


class MyCollaborationListResponse(BaseModel):
    items: List[MyCollaborationItem]
    total: int