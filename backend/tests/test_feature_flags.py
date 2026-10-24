"""Tests for feature flags: service logic, guards, and admin security."""

import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import Identity
from app.models.base import Base
from app.models.feature_flag import FeatureFlag
from app.services.feature_flag_service import (
    ALLOWED_FEATURE_KEYS,
    FeatureFlagService,
)


@pytest.fixture
def db_session():
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    session = sessionmaker(bind=eng)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def seeded_db(db_session):
    for key in ALLOWED_FEATURE_KEYS:
        db_session.add(FeatureFlag(key=key, enabled=True, description=key))
    db_session.commit()
    return db_session


def _admin_request(user_id=1):
    req = MagicMock()
    req.state.user = {"identity": Identity.ADMIN, "id": user_id}
    req.state.user_id = user_id
    return req


def _user_request():
    req = MagicMock()
    req.state.user = {"identity": Identity.USER, "id": 2}
    req.state.user_id = 2
    return req


class TestFeatureFlagService:
    def test_default_when_missing(self, db_session):
        assert FeatureFlagService(db_session).is_enabled("nope", default=True) is True
        assert FeatureFlagService(db_session).is_enabled("nope", default=False) is False

    def test_toggle(self, seeded_db):
        svc = FeatureFlagService(seeded_db)
        assert svc.is_enabled("allow_registration") is True
        svc.set_enabled("allow_registration", False)
        assert svc.is_enabled("allow_registration") is False

    def test_set_unknown_key_rejected(self, seeded_db):
        with pytest.raises(ValueError):
            FeatureFlagService(seeded_db).set_enabled("evil_key", False)

    def test_public_flags_only_two_keys(self, seeded_db):
        flags = FeatureFlagService(seeded_db).public_flags()
        assert set(flags.keys()) == {"allow_registration", "enable_verification_email"}
        assert "enable_auth_code_email" not in flags

    def test_registration_close_links_verification_email(self, seeded_db):
        svc = FeatureFlagService(seeded_db)
        assert svc.effective_enabled("enable_verification_email") is True
        svc.set_enabled("allow_registration", False)
        assert svc.effective_enabled("enable_verification_email") is False
        assert svc.public_flags()["enable_verification_email"] is False
        # stored value untouched: reopening registration restores it
        assert svc.is_enabled("enable_verification_email") is True
        svc.set_enabled("allow_registration", True)
        assert svc.effective_enabled("enable_verification_email") is True

    def test_verification_email_off_does_not_affect_registration(self, seeded_db):
        svc = FeatureFlagService(seeded_db)
        svc.set_enabled("enable_verification_email", False)
        assert svc.effective_enabled("allow_registration") is True


class TestSettingsApiSecurity:
    def test_anonymous_list_denied(self, seeded_db):
        from app.api.v1.settings import list_feature_flags
        import asyncio

        req = MagicMock()
        req.state = object()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(list_feature_flags(request=req, db=seeded_db))
        assert exc.value.status_code == 401

    def test_non_admin_list_denied(self, seeded_db):
        from app.api.v1.settings import list_feature_flags
        import asyncio
        with pytest.raises(HTTPException) as exc:
            asyncio.run(list_feature_flags(request=_user_request(), db=seeded_db))
        assert exc.value.status_code == 403

    def test_admin_list_ok(self, seeded_db):
        from app.api.v1.settings import list_feature_flags
        import asyncio
        result = asyncio.run(list_feature_flags(request=_admin_request(), db=seeded_db))
        assert {f["key"] for f in result} == set(ALLOWED_FEATURE_KEYS)

    def test_update_unknown_key_400(self, seeded_db):
        from app.api.v1.settings import update_feature_flag
        from app.schemas.feature_flag import FeatureFlagUpdate
        import asyncio
        with pytest.raises(HTTPException) as exc:
            asyncio.run(update_feature_flag(
                key="evil", payload=FeatureFlagUpdate(enabled=True),
                request=_admin_request(), db=seeded_db,
            ))
        assert exc.value.status_code == 400

    def test_update_by_user_denied(self, seeded_db):
        from app.api.v1.settings import update_feature_flag
        from app.schemas.feature_flag import FeatureFlagUpdate
        import asyncio
        with pytest.raises(HTTPException) as exc:
            asyncio.run(update_feature_flag(
                key="allow_registration", payload=FeatureFlagUpdate(enabled=False),
                request=_user_request(), db=seeded_db,
            ))
        assert exc.value.status_code == 403

    def test_update_toggle_persists(self, seeded_db):
        from app.api.v1.settings import update_feature_flag
        from app.schemas.feature_flag import FeatureFlagUpdate
        import asyncio
        result = asyncio.run(update_feature_flag(
            key="allow_registration", payload=FeatureFlagUpdate(enabled=False),
            request=_admin_request(), db=seeded_db,
        ))
        assert result == {"key": "allow_registration", "enabled": False}


class TestQuotaSelfEdit:
    def _call(self, db, admin_id, target_id, target_identity):
        from app.api.v1.accounts import admin_update_quota
        from app.models.account import Account
        target = Account(
            name=f"u{target_id}", password="p", email=f"u{target_id}@x.io",
            identity=target_identity,
        )
        target.id = target_id
        db.add(target)
        db.commit()
        req = _admin_request(admin_id)
        import asyncio
        return asyncio.run(
            admin_update_quota(
                request=req, user_id=target_id, total_storage=123,
                db=db, redis_client=MagicMock(),
            )
        )

    def test_admin_can_update_own_quota(self, db_session):
        result = self._call(db_session, admin_id=9, target_id=9, target_identity=Identity.ADMIN)
        assert result["total_storage"] == 123

    def test_admin_cannot_update_other_admin(self, db_session):
        with pytest.raises(HTTPException) as exc:
            self._call(db_session, admin_id=9, target_id=10, target_identity=Identity.ADMIN)
        assert exc.value.status_code == 403

    def test_admin_can_update_normal_user(self, db_session):
        result = self._call(db_session, admin_id=9, target_id=11, target_identity=Identity.USER)
        assert result["total_storage"] == 123
