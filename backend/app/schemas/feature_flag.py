from pydantic import BaseModel


class FeatureFlagUpdate(BaseModel):
    enabled: bool
