"""Tests for admin API endpoints (_admin_required function)."""

import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from app.constants import Identity


class TestAdminRequired:
    """Test the _admin_required dependency function."""

    def test_no_user_state_returns_401(self):
        from app.api.v1.accounts import _admin_required

        req = MagicMock()
        req.state = object()
        with pytest.raises(HTTPException) as e:
            _admin_required(req)
        assert e.value.status_code == 401

    def test_non_admin_returns_403(self):
        from app.api.v1.accounts import _admin_required

        req = MagicMock()
        req.state.user = {"identity": Identity.USER}
        with pytest.raises(HTTPException) as e:
            _admin_required(req)
        assert e.value.status_code == 403

    def test_admin_succeeds(self):
        """Admin should return the user dict directly."""
        from app.api.v1.accounts import _admin_required

        req = MagicMock()
        req.state.user = {"identity": Identity.ADMIN}
        result = _admin_required(req)
        assert result == {"identity": Identity.ADMIN}
import pytest
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.constants import Identity
from app.models.account import Account


@pytest.fixture
def db_session():
    from app.models.base import Base
    eng = create_engine("sqlite://")
    Base.metadata.create_all(bind=eng)
    sess = sessionmaker(bind=eng)()
    try:
        yield sess
    finally:
        sess.close()


@pytest.fixture
def admin_request():
    req = MagicMock()
    req.state.user = {"identity": Identity.ADMIN}
    return req


@pytest.fixture
def mock_redis():
    r = MagicMock()
    r.exists = lambda x: False
    r.delete = lambda x: 1
    return r


def cu(db, name, email, ident=Identity.USER, enb=True, tfs=0):
    u = Account(name=name, password="pw", email=email, identity=ident, enable=enb, total_file_size=tfs)
    db.add(u)
    db.flush()
    return u


class TestAdminListUsers4:
    @pytest.mark.asyncio
    async def test_empty(self, admin_request, db_session):
        from app.api.v1.accounts import admin_list_users
        r = await admin_list_users(admin_request, 1, 10, "", db_session, "mock")
        assert r["users"] == []

    @pytest.mark.asyncio
    async def test_excludes_admins(self, admin_request, db_session):
        from app.api.v1.accounts import admin_list_users
        from app.models.account import Account
        from unittest.mock import MagicMock as MM
        mockredis = MM()
        mockredis.exists.return_value = False
        mockredis.delete.return_value = 1
        u1 = Account(name="n1", password="pw", email="n1@t.com", identity=0)
        u2 = Account(name="n2", password="pw", email="n2@t.com", identity=0)
        ad = Account(name="ad", password="pw", email="ad@t.com", identity=1)
        for u in [u1, u2, ad]:
            db_session.add(u)
        db_session.flush()
        r = await admin_list_users(admin_request, 1, 10, "", db_session, mockredis)
        assert r["total"] == 2

    @pytest.mark.asyncio
    async def test_search_by_name(self, admin_request, db_session):
        from app.api.v1.accounts import admin_list_users
        from unittest.mock import MagicMock as MM
        cu(db_session, "alice", "alice@t.com", 0)
        cu(db_session, "bob", "bob@t.com")
        mockr = MM()
        mockr.exists.return_value = False
        r = await admin_list_users(admin_request, 1, 10, "ali", db_session, mockr)
        assert len(r["users"]) == 1
        assert r["users"][0]["username"] == "alice"

    @pytest.mark.asyncio
    async def test_search_by_email(self, admin_request, db_session):
        from app.api.v1.accounts import admin_list_users
        from unittest.mock import MagicMock
        cu(db_session, "u1", "hello@world.com", 0)
        r = await admin_list_users(admin_request, 1, 10, "hello", db_session,  MagicMock())
        assert len(r["users"]) == 1

    @pytest.mark.asyncio
    async def test_search_no_match(self, admin_request, db_session):
        from app.api.v1.accounts import admin_list_users
        from unittest.mock import MagicMock
        cu(db_session, "u1", "u1@t.com", 0)
        r = await admin_list_users(admin_request, 1, 10, "xxxxxxxxxx", db_session, MagicMock())
        assert r["users"] == []


class TestAdminUpdateQuota:
    @pytest.mark.asyncio
    async def test_success(self, admin_request, db_session):
        from app.api.v1.accounts import admin_update_quota
        from unittest.mock import MagicMock
        u = Account(name="u1", password="pw", email="u1@t.com", identity=0, total_file_size=100)
        db_session.add(u)
        db_session.flush()
        r = await admin_update_quota(admin_request, u.id, 500, db_session, MagicMock())
        assert r["total_storage"] == 500

    @pytest.mark.asyncio
    async def test_nonexistent_404(self, admin_request, db_session):
        from app.api.v1.accounts import admin_update_quota
        from unittest.mock import MagicMock
        with pytest.raises(HTTPException) as e:
            await admin_update_quota(admin_request, 99999, 500, db_session, MagicMock())
        assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_rejected_403(self, admin_request, db_session):
        from app.api.v1.accounts import admin_update_quota
        from unittest.mock import MagicMock
        u = Account(name="ad", password="pw", email="ad@t.com", identity=1)
        db_session.add(u)
        db_session.flush()
        with pytest.raises(HTTPException) as e:
            await admin_update_quota(admin_request, u.id, 500, db_session, MagicMock())
        assert e.value.status_code == 403


class TestAdminForceLogout:
    @pytest.mark.asyncio
    async def test_success(self, admin_request, db_session):
        from app.api.v1.accounts import admin_force_logout
        from unittest.mock import MagicMock
        u = Account(name="u2", password="pw", email="u2@t.com", identity=0)
        db_session.add(u)
        db_session.flush()
        mr = MagicMock()
        mr.delete.return_value = 1
        await admin_force_logout(admin_request, u.id, db_session, mr)
        assert mr.delete.call_count >= 1

    @pytest.mark.asyncio
    async def test_nonexistent_404(self, admin_request, db_session):
        from app.api.v1.accounts import admin_force_logout
        from unittest.mock import MagicMock
        with pytest.raises(HTTPException) as e:
            await admin_force_logout(admin_request, 99999, db_session, MagicMock())
        assert e.value.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_rejected_403(self, admin_request, db_session):
        from app.api.v1.accounts import admin_force_logout
        from unittest.mock import MagicMock
        ad = Account(name="ad", password="pw", email="ad@t.com", identity=1)
        db_session.add(ad)
        db_session.flush()
        with pytest.raises(HTTPException) as e:
            await admin_force_logout(admin_request, ad.id, db_session, MagicMock())
        assert e.value.status_code == 403


class TestAdminToggleEnable:
    @pytest.mark.asyncio
    async def test_toggle_off(self, admin_request, db_session):
        from app.api.v1.accounts import admin_toggle_enable
        from unittest.mock import MagicMock
        u = Account(name="u3", password="pw", email="u3@t.com", identity=0, enable=True)
        db_session.add(u)
        db_session.flush()
        r = await admin_toggle_enable(admin_request, u.id, db_session, MagicMock())
        assert r["enabled"] is False

    @pytest.mark.asyncio
    async def test_toggle_on(self, admin_request, db_session):
        from app.api.v1.accounts import admin_toggle_enable
        from unittest.mock import MagicMock
        u = Account(name="u4", password="pw", email="u4@t.com", identity=0, enable=False)
        db_session.add(u)
        db_session.flush()
        r = await admin_toggle_enable(admin_request, u.id, db_session, MagicMock())
        assert r["enabled"] is True
