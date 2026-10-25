from sqlalchemy import Column, String, Boolean
from .base import BaseModel


class FeatureFlag(BaseModel):
    __tablename__ = "feature_flags"

    key = Column(String(64), unique=True, nullable=False, index=True)
    enabled = Column(Boolean, nullable=False, default=True)
    description = Column(String(255), nullable=True)
