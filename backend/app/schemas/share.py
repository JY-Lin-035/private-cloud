from pydantic import BaseModel
from typing import Optional


class ShareItem(BaseModel):
    name: str
    path: str
    link: str
    date: str
    type: str  # 'folder' or 'file'


class ShareListResponse(BaseModel):
    share: list[ShareItem]


class ShareLinkRequest(BaseModel):
    item_uuid: str
    item_type: str  # 'folder' or 'file'


class ShareLinkResponse(BaseModel):
    link: str


class ShareDeleteResponse(BaseModel):
    message: str
