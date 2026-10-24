from app.database import SessionLocal
from app.repositories.feature_flag_repository import FeatureFlagRepository

ALLOWED_FEATURE_KEYS = (
    "allow_registration",
    "enable_verification_email",
    "enable_auth_code_email",
)

PUBLIC_FEATURE_KEYS = (
    "allow_registration",
    "enable_verification_email",
)


class FeatureFlagService:
    def __init__(self, db):
        self.repo = FeatureFlagRepository(db)

    def is_enabled(self, key: str, default: bool = True) -> bool:
        """Read a flag; unknown key falls back to default (fail-open)."""
        flag = self.repo.get_by_key(key)
        return bool(flag.enabled) if flag else default

    def set_enabled(self, key: str, enabled: bool):
        if key not in ALLOWED_FEATURE_KEYS:
            raise ValueError(f"Unknown feature key: {key}")
        return self.repo.set_enabled(key, enabled)

    def list_flags(self):
        return self.repo.list_all()

    def public_flags(self) -> dict:
        """Flags safe to expose to anonymous visitors."""
        return {key: self.is_enabled(key) for key in PUBLIC_FEATURE_KEYS}


def is_feature_enabled(key: str, default: bool = True) -> bool:
    """Self-contained flag check for callers without a request session."""
    db = SessionLocal()
    try:
        return FeatureFlagService(db).is_enabled(key, default)
    finally:
        db.close()
