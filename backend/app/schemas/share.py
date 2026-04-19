from pydantic import BaseModel
from typing import Optional


class ShareItem(BaseModel):
    name: str
    path: str
    link: str
    date: str


class ShareListResponse(BaseModel):
    share: list[ShareItem]


class ShareLinkRequest(BaseModel):
    dir: str
    filename: str


class ShareLinkResponse(BaseModel):
    link: str


class ShareDeleteResponse(BaseModel):
    message: str
