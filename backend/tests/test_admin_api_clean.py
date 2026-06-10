"""Tests for admin API endpoints (list users, update quota, force logout, toggle enable)."""

import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException
from app.constants import Identity
from app.models.account import Account


@pytest.fixture
def db_session():
    from app.models.base import Base
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    session = sessionmaker(bind=eng)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def admin_request():
    req = MagicMock()
    req.state.user = {"identity": Identity.ADMIN}
    return req


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.exists.return_value = False
    r.delete.return_value = 1
    return r


def _create_user(db, name, email, identity=Identity.USER, enable=True, total_file_size=0, used_size=0):
    u = Account(
        name=name,
        password="pwd",
        email=email,
        identity=identity,
        enable=enable,
        total_file_size=total_file_size,
        used_size=used_size,
    )
    db.add(u)
    db.flush()
    db.refresh(u)
    return u


class TestAdminRequired:
    def test_no_state_401(self):
        from app.api.v1.accounts import _admin_required
        req = MagicMock()
        req.state = object()
        with pytest.raises(HTTPException) as e:
            _admin_required(req)
        assert e.value.status_code == 401

    def test_user_403(self):
        from app.api.v1.accounts import _admin_required
        req = MagicMock()
        req.state.user = {"identity": Identity.USER}
        with pytest.raises(HTTPException) as e:
            _admin_required(req)
        assert e.value.status_code == 403

    def test_admin_200(self):
        from app.api.v1.accounts import _admin_required
        req = MagicMock()
        req.state.user = {"identity": Identity.ADMIN}
        result = _admin_required(req)
        assert result == {"identity": Identity.ADMIN}