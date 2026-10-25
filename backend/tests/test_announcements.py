"""Tests for announcements: CRUD, guards, expiry filtering, limits."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import Identity
from app.models.base import Base
from app.models.account import Account
from app.models.announcement import Announcement
from app.api.v1 import announcements as api


@pytest.fixture
def env():
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    admin = Account(name="adm", password="p", email="a@x.io", identity=Identity.ADMIN)
    admin.id = 1
    db.add(admin); db.commit()
    yield {"db": db}
    db.close()


def admin_req():
    req = MagicMock()
    req.state.user = {"identity": Identity.ADMIN, "id": 1}
    return req


def user_req():
    req = MagicMock()
    req.state.user = {"identity": Identity.USER, "id": 2}
    return req


def anon_req():
    req = MagicMock()
    req.state = object()
    return req


def mk(content, enabled=True, expires=None):
    return api.AnnouncementCreate(content=content, enabled=enabled, expires_at=expires)


class TestGuards:
    def test_anonymous_cannot_list(self, env):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api.admin_list(request=anon_req(), db=env["db"]))
        assert exc.value.status_code == 401

    def test_user_cannot_admin(self, env):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api.admin_create(request_=mk("x"), request=user_req(), db=env["db"]))
        assert exc.value.status_code == 403

    def test_user_can_read_active(self, env):
        asyncio.run(api.admin_create(request_=mk("系统维护通知"), request=admin_req(), db=env["db"]))
        r = asyncio.run(api.active_announcements(db=env["db"], user_id=2))
        assert r == {"announcements": ["系统维护通知"]}

    def test_active_route_requires_login(self):
        route = next(r for r in api.router.routes if r.path.endswith('/announcements') and "GET" in r.methods)
        deps = [d.call for d in route.dependant.dependencies]
        from app.api.dependencies import get_current_user_id
        assert get_current_user_id in deps


class TestLifecycle:
    def test_expiry_filtering(self, env):
        asyncio.run(api.admin_create(request_=mk("indefinite"), request=admin_req(), db=env["db"]))
        past = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        future = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        asyncio.run(api.admin_create(request_=mk("gone", expires=past), request=admin_req(), db=env["db"]))
        asyncio.run(api.admin_create(request_=mk("alive", expires=future), request=admin_req(), db=env["db"]))
        active = asyncio.run(api.active_announcements(db=env["db"]))["announcements"]
        assert "gone" not in active
        assert "indefinite" in active and "alive" in active
        listed = asyncio.run(api.admin_list(request=admin_req(), db=env["db"]))["announcements"]
        by_id = {a["content"]: a for a in listed}
        assert by_id["gone"]["expired"] is True and by_id["gone"]["effective"] is False
        assert by_id["alive"]["expired"] is False

    def test_update_and_clear_expiry(self, env):
        rid = asyncio.run(api.admin_create(request_=mk("tmp"), request=admin_req(), db=env["db"]))["id"]
        future = (datetime.utcnow() + timedelta(hours=2)).isoformat()
        asyncio.run(api.admin_update(item_id=rid, payload=api.AnnouncementUpdate(expires_at=future), request=admin_req(), db=env["db"]))
        a = env["db"].get(Announcement, rid)
        assert a.expires_at is not None
        asyncio.run(api.admin_update(item_id=rid, payload=api.AnnouncementUpdate(expires_at=""), request=admin_req(), db=env["db"]))
        assert env["db"].get(Announcement, rid).expires_at is None

    def test_disable_hides_from_ticker(self, env):
        rid = asyncio.run(api.admin_create(request_=mk("quiet"), request=admin_req(), db=env["db"]))["id"]
        asyncio.run(api.admin_update(item_id=rid, payload=api.AnnouncementUpdate(enabled=False), request=admin_req(), db=env["db"]))
        assert "quiet" not in asyncio.run(api.active_announcements(db=env["db"]))["announcements"]

    def test_delete(self, env):
        rid = asyncio.run(api.admin_create(request_=mk("del"), request=admin_req(), db=env["db"]))["id"]
        asyncio.run(api.admin_delete(item_id=rid, request=admin_req(), db=env["db"]))
        assert env["db"].get(Announcement, rid) is None

    def test_validation_length_and_control_chars(self, env):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api.admin_create(request_=mk("x" * 501), request=admin_req(), db=env["db"]))
        assert exc.value.status_code == 400
        asyncio.run(api.admin_create(request_=mk("line1\nline2\x07!"), request=admin_req(), db=env["db"]))
        contents = asyncio.run(api.active_announcements(db=env["db"]))["announcements"]
        assert all("\n" not in c and "\x07" not in c for c in contents)

    def test_max_active_limit(self, env):
        for i in range(20):
            asyncio.run(api.admin_create(request_=mk(f"n{i}"), request=admin_req(), db=env["db"]))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api.admin_create(request_=mk("21st"), request=admin_req(), db=env["db"]))
        assert exc.value.status_code == 400
