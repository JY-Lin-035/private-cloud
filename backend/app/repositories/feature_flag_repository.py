from typing import List, Optional
from app.models.feature_flag import FeatureFlag
from app.repositories.base_repository import BaseRepository


class FeatureFlagRepository(BaseRepository[FeatureFlag]):
    def __init__(self, db):
        super().__init__(FeatureFlag, db)

    def get_by_key(self, key: str) -> Optional[FeatureFlag]:
        """Get a feature flag by its unique key."""
        return self.get_by_field('key', key)

    def list_all(self) -> List[FeatureFlag]:
        """List all feature flags ordered by id."""
        return list(self.db.query(FeatureFlag).order_by(FeatureFlag.id).all())

    def set_enabled(self, key: str, enabled: bool) -> Optional[FeatureFlag]:
        """Toggle a feature flag. Returns None if the key does not exist."""
        flag = self.get_by_key(key)
        if not flag:
            return None
        flag.enabled = enabled
        self.db.commit()
        self.db.refresh(flag)
        return flag
