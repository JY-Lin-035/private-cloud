"""Tests for password-protected share links (M1)."""

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import Identity
from app.models.base import Base
from app.models.account import Account
from app.models.file import File
from app.models.folder import Folder
from app.services.share_service import ShareService


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
def env(db_session):
    user = Account(name="owner", password="p", email="o@x.io", identity=Identity.ADMIN)
    user.id = 1
    f = File(uuid="f-uuid-1", name="a.txt", size=10, owner_id=1, storage_path="/nonexistent/a.txt")
    d = Folder(uuid="d-uuid-1", name="dir", owner_id=1, size=0)
    db_session.add_all([user, f, d])
    db_session.commit()
    return {"db": db_session, "user": user, "file": f, "folder": d}


def _svc(env):
    return ShareService(env["db"])


class TestCreateLinkPassword:
    def test_set_password_hashes(self, env):
        r = _svc(env).create_link(1, "f-uuid-1", "file", password="S3cret!pw")
        assert r["stateCode"] == 200
        assert env["file"].share_password and "S3cret" not in env["file"].share_password

    def test_empty_string_clears(self, env):
        _svc(env).create_link(1, "f-uuid-1", "file", password="abc")
        _svc(env).create_link(1, "f-uuid-1", "file", password="")
        assert env["file"].share_password is None

    def test_none_keeps_existing(self, env):
        _svc(env).create_link(1, "f-uuid-1", "file", password="abc")
        stored = env["file"].share_password
        _svc(env).create_link(1, "f-uuid-1", "file", limited_date=datetime(2099, 1, 1))
        assert env["file"].share_password == stored

    def test_delete_link_clears_password(self, env):
        _svc(env).create_link(1, "d-uuid-1", "folder", password="abc")
        _svc(env).delete_link(1, "d-uuid-1", "folder")
        assert env["folder"].share_password is None

    def test_list_exposes_has_password_not_hash(self, env):
        link = _svc(env).create_link(1, "f-uuid-1", "file", password="abc")["url"]
        item = next(i for i in _svc(env).get_list(1)["list"] if i["uuid"] == "f-uuid-1")
        assert item["has_password"] is True
        assert "share_password" not in item


class TestStatusAndVerify:
    def test_unknown_link_minimal_info(self, env):
        st = _svc(env).get_share_status("nope")
        assert st == {"exists": False, "type": None, "password_required": False, "expired": False,
                      "stateCode": 200}

    def test_password_required_flag(self, env):
        link = _svc(env).create_link(1, "f-uuid-1", "file", password="abc")["url"]
        st = _svc(env).get_share_status(link)
        assert st["exists"] and st["password_required"] and not st["expired"]

    def test_expired_flag(self, env):
        link = _svc(env).create_link(
            1, "f-uuid-1", "file",
            limited_date=datetime.utcnow() + timedelta(hours=8) - timedelta(days=1),
        )["url"]
        # limited_date stored as local time; set in the past
        assert _svc(env).get_share_status(link)["expired"] is True

    def test_verify_wrong_password_403(self, env):
        link = _svc(env).create_link(1, "f-uuid-1", "file", password="right")["url"]
        r = _svc(env).verify_share_password(link, "wrong")
        assert r["stateCode"] == 403

    def test_verify_correct_returns_ticket(self, env):
        link = _svc(env).create_link(1, "f-uuid-1", "file", password="right")["url"]
        r = _svc(env).verify_share_password(link, "right")
        assert r["stateCode"] == 200 and r["ticket"] and r["expires_in"] == 900

    def test_verify_on_open_link_404(self, env):
        link = _svc(env).create_link(1, "f-uuid-1", "file")["url"]
        assert _svc(env).verify_share_password(link, "whatever")["stateCode"] == 404


class TestDownloadGate:
    def test_protected_without_ticket_428(self, env):
        link = _svc(env).create_link(1, "f-uuid-1", "file", password="abc")["url"]
        r = _svc(env).download(link)
        assert r["stateCode"] == 428

    def test_protected_with_ticket_passes_gate(self, env):
        link = _svc(env).create_link(1, "f-uuid-1", "file", password="abc")["url"]
        ticket = _svc(env).verify_share_password(link, "abc")["ticket"]
        r = _svc(env).download(link, ticket=ticket)
        # gate passed; next error is the missing physical file (storage not seeded)
        assert r["stateCode"] != 428

    def test_open_link_unaffected(self, env):
        link = _svc(env).create_link(1, "f-uuid-1", "file")["url"]
        r = _svc(env).download(link)
        assert r["stateCode"] != 428

    def test_folder_protected_gates_before_unsupported(self, env):
        link = _svc(env).create_link(1, "d-uuid-1", "folder", password="abc")["url"]
        assert _svc(env).download(link)["stateCode"] == 428

    def test_ticket_not_reusable_across_links(self, env):
        f2 = File(uuid="f-uuid-2", name="b.txt", size=1, owner_id=1, storage_path="/nonexistent/b.txt")
        env["db"].add(f2)
        env["db"].commit()
        l1 = _svc(env).create_link(1, "f-uuid-1", "file", password="a")["url"]
        l2 = _svc(env).create_link(1, "f-uuid-2", "file", password="a")["url"]
        t1 = _svc(env).verify_share_password(l1, "a")["ticket"]
        assert _svc(env).download(l2, ticket=t1)["stateCode"] == 428


class TestRouterHandlers:
    def test_status_handler_shape(self, env):
        from app.api.v1.share import share_status, ShareStatusRequest
        link = _svc(env).create_link(1, "f-uuid-1", "file", password="abc")["url"]
        r = asyncio.run(share_status(request=ShareStatusRequest(link=link), db=env["db"]))
        assert set(r.keys()) == {"exists", "type", "password_required", "expired"}

    def test_verify_handler_issues_ticket_and_password_never_in_response(self, env):
        from app.api.v1.share import share_verify_password, ShareVerifyRequest
        link = _svc(env).create_link(1, "f-uuid-1", "file", password="abc")["url"]
        redis = MagicMock()
        redis.get.return_value = None
        r = asyncio.run(share_verify_password(
            request=ShareVerifyRequest(link=link, password="abc"), db=env["db"], redis_client=redis))
        assert set(r.keys()) == {"ticket", "expires_in"}
        assert "abc" not in str(r)
        redis.delete.assert_called_once()

    def test_verify_handler_403_on_wrong_password(self, env):
        from app.api.v1.share import share_verify_password, ShareVerifyRequest
        link = _svc(env).create_link(1, "f-uuid-1", "file", password="abc")["url"]
        redis = MagicMock()
        redis.get.return_value = None
        redis.incr.return_value = 1
        with pytest.raises(HTTPException) as exc:
            asyncio.run(share_verify_password(
                request=ShareVerifyRequest(link=link, password="bad"), db=env["db"], redis_client=redis))
        assert exc.value.status_code == 403
        redis.incr.assert_called_once()
