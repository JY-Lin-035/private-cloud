"""Security regression tests for the hardening changes.

Covers: WS ticket issuance/authz, TUS upload ownership, folder-path IDOR,
email-change flow, uniform auth errors, session public-path exact matching,
Origin guard, and trusted client-IP extraction.
"""
import asyncio
import re
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


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


def _mk_account(db, name, email, password_hash="x", identity=0, enable=True,
                total=10 * 1024 * 1024, used=0, signal=5 * 1024 * 1024):
    from app.models.account import Account
    a = Account(
        name=name, password=password_hash, email=email,
        signal_file_size=signal, total_file_size=total, used_size=used,
        identity=identity, enable=enable, email_verified_at=datetime.utcnow(),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _mk_file(db, owner_id, uuid_val, name="a.txt"):
    from app.models.file import File
    f = File(uuid=uuid_val, owner_id=owner_id, parent_folder_id=None,
             name=name, size=0, mime_type="text/plain", storage_path="/tmp/x")
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


# ---------------------------------------------------------------- WS ticket

class TestWsTicket:
    def test_owner_gets_ticket(self, db_session):
        from app.api.v1.collaboration import issue_ws_ticket
        from app.schemas.collaboration import WsTicketRequest
        owner = _mk_account(db_session, "owner", "o@x.com")
        f = _mk_file(db_session, owner.id, "11111111-1111-1111-1111-111111111111")
        redis = MagicMock()
        out = issue_ws_ticket(WsTicketRequest(file_uuid=f.uuid), db_session, redis, owner.id)
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}", out["ticket"])
        redis.setex.assert_called_once()
        key, ttl, val = redis.setex.call_args[0]
        assert key == f"wsTicket:{out['ticket']}"
        assert ttl == 60
        assert val == f"{owner.id}:{f.uuid}"

    def test_stranger_forbidden(self, db_session):
        from fastapi import HTTPException
        from app.api.v1.collaboration import issue_ws_ticket
        from app.schemas.collaboration import WsTicketRequest
        owner = _mk_account(db_session, "owner", "o@x.com")
        other = _mk_account(db_session, "other", "e@x.com")
        f = _mk_file(db_session, owner.id, "22222222-2222-2222-2222-222222222222")
        with pytest.raises(HTTPException) as e:
            issue_ws_ticket(WsTicketRequest(file_uuid=f.uuid), db_session, MagicMock(), other.id)
        assert e.value.status_code == 403

    def test_collaborator_gets_ticket(self, db_session):
        from app.api.v1.collaboration import issue_ws_ticket
        from app.schemas.collaboration import WsTicketRequest
        from app.models.collaboration import Collaboration
        owner = _mk_account(db_session, "owner", "o@x.com")
        mate = _mk_account(db_session, "mate", "m@x.com")
        f = _mk_file(db_session, owner.id, "33333333-3333-3333-3333-333333333333")
        db_session.add(Collaboration(file_uuid=f.uuid, owner_id=owner.id,
                                     collaborator_id=mate.id, permission="editor"))
        db_session.commit()
        out = issue_ws_ticket(WsTicketRequest(file_uuid=f.uuid), db_session, MagicMock(), mate.id)
        assert out["ticket"]

    def test_deleted_file_404(self, db_session):
        from fastapi import HTTPException
        from app.api.v1.collaboration import issue_ws_ticket
        from app.schemas.collaboration import WsTicketRequest
        owner = _mk_account(db_session, "owner", "o@x.com")
        f = _mk_file(db_session, owner.id, "44444444-4444-4444-4444-444444444444")
        f.deleted_at = datetime.utcnow()
        db_session.commit()
        with pytest.raises(HTTPException) as e:
            issue_ws_ticket(WsTicketRequest(file_uuid=f.uuid), db_session, MagicMock(), owner.id)
        assert e.value.status_code == 404


class TestWsProtocol:
    def test_subprotocol_constant(self):
        from app.api.v1.collab_ws import WS_SUBPROTOCOL
        assert WS_SUBPROTOCOL == "meowcloud-collab.v1"
        assert re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", WS_SUBPROTOCOL)

    def test_b64_len_rejects_garbage_and_oversize(self):
        from app.api.v1.collab_ws import _b64_len
        assert _b64_len("not base64!!") is None
        assert _b64_len("aGVsbG8=") == 5
        assert _b64_len("A" * (3 * 1024 * 1024)) is None  # over encoded cap


# ---------------------------------------------------------------- TUS ownership

class TestTusOwnership:
    def test_cross_user_denied(self, db_session, tmp_path, monkeypatch):
        from app.config import settings
        from app.services.file_service import FileService
        monkeypatch.setattr(settings, "STORAGE_BASE_PATH", str(tmp_path))
        owner = _mk_account(db_session, "owner", "o@x.com")
        other = _mk_account(db_session, "other", "e@x.com")
        svc = FileService(db_session)
        created = svc.create_tus_upload(owner.id, None, "t.txt", 4)
        uid = created["upload_id"]

        assert svc.get_tus_upload(uid, other.id)["stateCode"] == 404
        assert svc.append_tus_chunk(uid, 0, b"ab", other.id)["stateCode"] == 404
        assert svc.finalize_tus_upload(uid, other.id)["stateCode"] == 404

        # owner works
        assert svc.append_tus_chunk(uid, 0, b"ab", owner.id)["offset"] == 2
        assert svc.get_tus_upload(uid, owner.id)["offset"] == 2

    def test_chunk_clamped_to_declared_length(self, db_session, tmp_path, monkeypatch):
        from app.config import settings
        from app.services.file_service import FileService
        monkeypatch.setattr(settings, "STORAGE_BASE_PATH", str(tmp_path))
        owner = _mk_account(db_session, "owner", "o@x.com")
        svc = FileService(db_session)
        uid = svc.create_tus_upload(owner.id, None, "t.txt", 3)["upload_id"]
        r = svc.append_tus_chunk(uid, 0, b"abcdefgh", owner.id)
        assert r["offset"] == 3  # cannot exceed declared Upload-Length


# ---------------------------------------------------------------- folder path

class TestFolderPathIdor:
    def test_other_users_folder_is_hidden(self, db_session):
        from fastapi import HTTPException
        from app.api.v1.folders import get_folder_path
        from app.models.folder import Folder
        owner = _mk_account(db_session, "owner", "o@x.com")
        other = _mk_account(db_session, "other", "e@x.com")
        folder = Folder(uuid="55555555-5555-5555-5555-555555555555", owner_id=owner.id,
                        parent_id=None, name="secret", size=0)
        db_session.add(folder)
        db_session.commit()
        with pytest.raises(HTTPException) as e:
            asyncio.run(get_folder_path(folder_uuid=folder.uuid, db=db_session, user_id=other.id))
        assert e.value.status_code == 404


# ---------------------------------------------------------------- email flow

class TestEmailChange:
    def test_code_read_from_new_address(self, db_session):
        from app.services.account_service import AccountService
        acct = _mk_account(db_session, "u", "old@x.com", password_hash="x")
        redis = MagicMock()
        redis.get.return_value = b"newcode"
        svc = AccountService(db_session, redis)
        res = svc.modify_email(acct.id, "new@x.com", "old@x.com", "newcode")
        assert res["stateCode"] == 200
        db_session.refresh(acct)
        assert acct.email == "new@x.com"
        redis.get.assert_any_call("mailCode:new@x.com")

    def test_wrong_code_rejected(self, db_session):
        from app.services.account_service import AccountService
        acct = _mk_account(db_session, "u2", "old2@x.com", password_hash="x")
        redis = MagicMock()
        redis.get.return_value = b"right"
        svc = AccountService(db_session, redis)
        res = svc.modify_email(acct.id, "new2@x.com", "old2@x.com", "wrong")
        assert res["stateCode"] == 403

    def test_duplicate_new_email_rejected(self, db_session):
        from app.services.account_service import AccountService
        a = _mk_account(db_session, "a", "a@x.com", password_hash="x")
        _mk_account(db_session, "b", "b@x.com", password_hash="x")
        redis = MagicMock()
        redis.get.return_value = b"code"
        svc = AccountService(db_session, redis)
        res = svc.modify_email(a.id, "b@x.com", "a@x.com", "code")
        assert res["stateCode"] == 409


class TestUniformAuthErrors:
    def test_login_messages_identical(self, db_session):
        from app.services.account_service import AccountService
        from app.utils.security import hash_password
        _mk_account(db_session, "real", "r@x.com", password_hash=hash_password("Correct#Pass1!"))
        svc = AccountService(db_session, MagicMock())
        missing = svc.login("nope", "whatever")
        wrong = svc.login("real", "badpass")
        assert missing["stateCode"] == wrong["stateCode"] == 401
        assert missing["error"] == wrong["error"]

    def test_get_code_uniform_message(self, db_session):
        from app.services.account_service import AccountService
        _mk_account(db_session, "real", "r2@x.com")
        redis = MagicMock()
        svc = AccountService(db_session, redis)
        exists = svc.get_code("r2@x.com", "pw")
        missing = svc.get_code("ghost@x.com", "pw")
        assert exists["message"] == missing["message"]
        assert "code" in exists and "code" not in missing


# ---------------------------------------------------------------- middleware

class TestSessionPublicPaths:
    def _m(self):
        from app.middleware.session_middleware import SessionMiddleware
        return SessionMiddleware.__new__(SessionMiddleware)

    def test_exact_paths(self):
        m = self._m()
        assert m._is_public("/api/files/download")
        assert m._is_public("/api/files/raw")
        assert m._is_public("/api/share/verifyPassword")
        assert m._is_public("/api/email/verify/1/abc")
        # must NOT be public
        assert not m._is_public("/api/files/downloadToken")
        assert not m._is_public("/api/files/downloadBulk")
        assert not m._is_public("/api/files/downloadXxx")
        assert not m._is_public("/api/accounts/admin/users")


class TestOriginGuard:
    def test_origin_rules(self):
        from app.middleware.origin_guard import _origin_ok, _has_session_cookie
        assert _origin_ok("https://meowcloud.jun.org.uk")
        assert _origin_ok("https://meowcloud-api.jun.org.uk")
        assert _origin_ok("https://meowcloud.jun.org.uk/some/path")  # referer
        assert not _origin_ok("https://evil.example")
        assert not _origin_ok(None)
        assert _has_session_cookie({"cookie": "a=1; session=2|tok"})
        assert not _has_session_cookie({"cookie": "a=1"})

    def _run(self, method, headers):
        from app.middleware.origin_guard import OriginGuardMiddleware

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        mw = OriginGuardMiddleware(app)
        scope = {
            "type": "http",
            "method": method,
            "path": "/api/x",
            "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        }
        out = {}

        async def receive():
            return {"type": "http.request"}

        async def send(message):
            if message["type"] == "http.response.start":
                out["status"] = message["status"]

        asyncio.run(mw(scope, receive, send))
        return out["status"]

    def test_blocks_evil_origin_with_session(self):
        assert self._run("POST", {"cookie": "session=2|tok", "origin": "https://evil.example"}) == 403

    def test_blocks_missing_origin_with_session(self):
        assert self._run("POST", {"cookie": "session=2|tok"}) == 403

    def test_allows_trusted_origin(self):
        assert self._run("POST", {"cookie": "session=2|tok",
                                  "origin": "https://meowcloud.jun.org.uk"}) == 200

    def test_allows_no_cookie(self):
        assert self._run("POST", {"origin": "https://evil.example"}) == 200

    def test_get_never_blocked(self):
        assert self._run("GET", {"cookie": "session=2|tok", "origin": "https://evil.example"}) == 200


class TestClientIp:
    def test_cf_only(self):
        from app.services.security_engine import get_client_ip
        assert get_client_ip({"cf-connecting-ip": "203.0.113.9"}) == "203.0.113.9"
        assert get_client_ip({"x-forwarded-for": "1.2.3.4"}) is None

    def test_session_cookie_helpers(self):
        from app.utils.session_auth import parse_session_cookie, split_session_value
        assert parse_session_cookie("a=1; session=7|tok") == "7|tok"
        assert split_session_value("7|tok") == (7, "7|tok")
        assert split_session_value("bad") is None


class TestDownloadTokenBinding:
    def test_token_for_other_file_rejected(self):
        from fastapi import HTTPException
        from app.api.v1.files import download_file
        redis = MagicMock()
        redis.exists.return_value = False
        redis.getdel.return_value = "1:some-other-file"
        with pytest.raises(HTTPException) as e:
            asyncio.run(download_file(file_uuid="target-file", token="tok",
                                      db=MagicMock(), redis=redis, user_id=None))
        assert e.value.status_code == 403

    def test_malformed_user_id_rejected(self):
        from fastapi import HTTPException
        from app.api.v1.files import download_file
        redis = MagicMock()
        redis.exists.return_value = False
        redis.getdel.return_value = "notint:target-file"
        with pytest.raises(HTTPException) as e:
            asyncio.run(download_file(file_uuid="target-file", token="tok",
                                      db=MagicMock(), redis=redis, user_id=None))
        assert e.value.status_code == 401


class TestResetUniform:
    def test_reset_errors_identical(self, db_session):
        from app.services.account_service import AccountService
        from app.utils.security import hash_password
        _mk_account(db_session, "res", "res@x.com", password_hash=hash_password("P@ssw0rd!abc"))
        redis = MagicMock()
        redis.get.return_value = b"rightcode"
        svc = AccountService(db_session, redis)
        ghost = svc.reset_password("ghost@x.com", "whatever", "NewP@ss1!xyz")
        wrong = svc.reset_password("res@x.com", "wrongcode", "NewP@ss1!xyz")
        assert ghost["stateCode"] == wrong["stateCode"] == 403
        assert ghost["error"] == wrong["error"]

class TestTusLocation:
    """Regression guard: tus Location MUST carry the public https scheme.

    Production bug (2026-10-31): cloudflared does not always send
    X-Forwarded-Proto, so url_for() emitted http:// Locations and every
    browser PATCH died on CSP connect-src / mixed content.
    """

    @staticmethod
    def _req(headers=None, scheme="http", host="testserver"):
        from starlette.requests import Request
        h = {"host": host, **(headers or {})}
        scope = {
            "type": "http", "method": "POST", "path": "/api/files/tus",
            "headers": [(k.lower().encode(), v.encode()) for k, v in h.items()],
            "scheme": scheme, "server": ("127.0.0.1", 8000),
            "query_string": b"", "client": ("127.0.0.1", 5555),
        }
        return Request(scope)

    def test_app_url_config_wins(self, monkeypatch):
        from app.api.v1 import files as F
        monkeypatch.setattr(F.settings, "APP_URL", "https://meowcloud-api.example.com/")
        loc = F._tus_location(self._req(), "ID1")
        assert loc == "https://meowcloud-api.example.com/api/files/tus/ID1"

    def test_cf_connecting_ip_implies_https(self, monkeypatch):
        from app.api.v1 import files as F
        monkeypatch.setattr(F.settings, "APP_URL", "")
        loc = F._tus_location(self._req({"cf-connecting-ip": "8.8.8.8"}), "ID2")
        assert loc.startswith("https://") and "testserver" in loc

    def test_xfp_header_authoritative_when_present(self, monkeypatch):
        from app.api.v1 import files as F
        monkeypatch.setattr(F.settings, "APP_URL", "")
        loc = F._tus_location(self._req({"x-forwarded-proto": "https"}), "ID3")
        assert loc.startswith("https://")

    def test_plain_loopback_dev_stays_http(self, monkeypatch):
        from app.api.v1 import files as F
        monkeypatch.setattr(F.settings, "APP_URL", "")
        loc = F._tus_location(self._req(), "ID4")
        assert loc == "http://testserver/api/files/tus/ID4"


class TestQuotaAndShareHardening:
    """Regression locks for red-team round-2 findings."""

    def test_recalc_includes_trashed(self, db_session, sample_account, sample_home_folder, mocker):
        # B2: used_size must count soft-deleted (trashed) files, since they
        # still occupy disk; excluding them lets users free quota for free.
        import uuid as _u
        from app.models.file import File
        from app.services.file_service import FileService
        from datetime import datetime
        live = File(uuid=str(_u.uuid4()), owner_id=sample_account.id,
                    parent_folder_id=sample_home_folder.uuid, name="live.txt",
                    size=1000, mime_type="text/plain", storage_path="x")
        trashed = File(uuid=str(_u.uuid4()), owner_id=sample_account.id,
                       parent_folder_id=sample_home_folder.uuid, name="gone.txt",
                       size=4000, mime_type="text/plain", storage_path="y",
                       deleted_at=datetime.utcnow())
        db_session.add_all([live, trashed]); db_session.commit()
        svc = FileService(db_session)
        svc.recalculate_used_storage(sample_account.id)
        db_session.refresh(sample_account)
        assert sample_account.used_size == 5000  # 1000 live + 4000 trashed

    def test_shared_file_in_trashed_folder_not_downloadable(self, db_session, sample_account, sample_home_folder, tmp_path, monkeypatch):
        # B1: a share link for a file whose folder was soft-deleted must be dead.
        import uuid as _u
        from app.models.file import File
        from app.models.folder import Folder
        from app.services.share_service import ShareService
        from app.config import settings
        monkeypatch.setattr(settings, "STORAGE_BASE_PATH", str(tmp_path))
        f = File(uuid=str(_u.uuid4()), owner_id=sample_account.id,
                 parent_folder_id="folder-x", name="s.txt", size=10,
                 mime_type="text/plain", storage_path="p")
        f.shared = "deadbeefdeadbeef"
        f.deleted_at = __import__("datetime").datetime.utcnow()  # trashed
        db_session.add(f); db_session.commit()
        svc = ShareService(db_session)
        res = svc.download("deadbeefdeadbeef")
        assert res and res.get("stateCode") in (404, 403)

    def test_login_password_length_bounded(self):
        # B5: reject absurdly long login inputs (Argon2/log DoS).
        from app.schemas.account import LoginRequest
        from pydantic import ValidationError
        try:
            LoginRequest.model_validate({"username": "u", "password": "x" * 5000})
            assert False, "should have rejected >128"
        except ValidationError:
            pass


class TestQuotaSharedHelper:
    """N1: all three recalc paths share one helper; it MUST count trash."""

    def test_recalc_user_storage_counts_trash(self, db_session, sample_account, sample_home_folder):
        import uuid as _u
        from datetime import datetime
        from app.models.file import File
        from app.services.quota import recalc_user_storage
        db_session.add_all([
            File(uuid=str(_u.uuid4()), owner_id=sample_account.id,
                 parent_folder_id=sample_home_folder.uuid, name="live", size=700,
                 mime_type="text/plain", storage_path="x"),
            File(uuid=str(_u.uuid4()), owner_id=sample_account.id,
                 parent_folder_id=sample_home_folder.uuid, name="gone", size=300,
                 mime_type="text/plain", storage_path="y", deleted_at=datetime.utcnow()),
        ])
        db_session.commit()
        total, nfolders = recalc_user_storage(db_session, sample_account)
        assert total == 1000  # includes the 300 trashed bytes
        assert sample_account.used_size == 1000
        assert nfolders >= 1


class TestTusIdValidation:
    def test_accepts_uuid4_rejects_traversal(self):
        import uuid as _u
        from app.services.file_service import FileService
        assert FileService._tus_id_ok(str(_u.uuid4())) is True
        for bad in ["", "..", "a" * 35, "a" * 37, "../..", "x" * 36, "550e8400-e29b-41d4-a716-44665544000"[:35]]:
            assert FileService._tus_id_ok(bad) is False, bad


class TestAuditSanitize:
    def test_clean_neutralizes_separators_and_bounds(self):
        from app.utils.security_log import _clean
        out = _clean("evil|LINE\n|FORGE\rx")
        assert "\n" not in out and "\r" not in out and "|" not in out
        assert len(_clean("x" * 5000)) == 300


class TestLoginCsrfGuard:
    import asyncio

    def _run(self, scope):
        import asyncio
        from app.middleware.origin_guard import OriginGuardMiddleware
        state = {"status": None, "passed_app": False}

        async def app(s, r, sd):
            state["passed_app"] = True

        async def send(msg):
            if msg["type"] == "http.response.start":
                state["status"] = msg["status"]

        mw = OriginGuardMiddleware(app)

        async def _go():
            await mw(scope, None, send)

        asyncio.run(_go())
        return state

    def _scope(self, path, origin=None, cookie=None):
        h = [(b"host", b"api.example.com")]
        if origin:
            h.append((b"origin", origin.encode()))
        if cookie:
            h.append((b"cookie", cookie.encode()))
        return {"type": "http", "method": "POST", "path": path, "headers": h, "client": ("1.2.3.4", 1)}

    def test_bad_origin_login_blocked_even_without_cookie(self, monkeypatch):
        from app.middleware.origin_guard import OriginGuardMiddleware
        from app.config import settings
        monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "https://good.test")
        st = self._run(self._scope("/api/accounts/login", origin="https://evil.test"))
        assert st["status"] == 403 and not st["passed_app"]

    def test_allowed_origin_login_passes(self, monkeypatch):
        from app.middleware.origin_guard import OriginGuardMiddleware
        from app.config import settings
        monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "https://good.test")
        st = self._run(self._scope("/api/accounts/login", origin="https://good.test"))
        assert st["passed_app"] and st["status"] is None

    def test_no_origin_nonbrowser_passes(self):
        st = self._run(self._scope("/api/accounts/login"))
        assert st["passed_app"] and st["status"] is None

    def test_unrelated_path_no_cookie_unchecked(self):
        st = self._run(self._scope("/api/share/downloadFile", origin="https://evil.test"))
        assert st["passed_app"]


class TestQuotaRecursiveFolderSize:
    """F1: recalc must set folder.size to the RECURSIVE subtree total,
    matching _update_parent_folder_size bookkeeping (permanent folder-delete
    subtracts folder.size from used_size on that basis)."""

    def test_parent_folder_size_includes_nested_children(self, db_session, sample_account, sample_home_folder):
        import uuid as _u
        from datetime import datetime
        from app.models.file import File
        from app.models.folder import Folder
        from app.services.quota import recalc_user_storage
        sub = Folder(uuid=str(_u.uuid4()), owner_id=sample_account.id,
                     parent_id=sample_home_folder.uuid, name="sub", size=0)
        db_session.add(sub); db_session.flush()
        db_session.add_all([
            File(uuid=str(_u.uuid4()), owner_id=sample_account.id,
                 parent_folder_id=sample_home_folder.uuid, name="root.txt",
                 size=100, mime_type="text/plain", storage_path="a"),
            File(uuid=str(_u.uuid4()), owner_id=sample_account.id,
                 parent_folder_id=sub.uuid, name="deep.txt",
                 size=900, mime_type="text/plain", storage_path="b",
                 deleted_at=datetime.utcnow()),  # trashed child must still count
        ])
        db_session.commit()
        used, n = recalc_user_storage(db_session, sample_account)
        db_session.refresh(sample_home_folder); db_session.refresh(sub)
        assert used == 1000
        assert sub.size == 900
        assert sample_home_folder.size == 1000  # recursive: own 100 + sub 900


class TestAccessLogCredentialFilter:
    """R6: uvicorn access-log masking must (a) redact link/token/ptk/ticket,
    (b) NOT break uvicorn's AccessFormatter (it unpacks record.args), and
    (c) never leak the long-lived share hash embedded in ticket=."""

    LINK = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    TICKET = LINK + ".1730000000.XyZsig"

    def _make_record(self, formatter_cls):
        import logging as _l
        # Contract copied from uvicorn 0.54 AccessFormatter.formatMessage:
        #   (client_addr, method, full_path, http_version, status_code)
        #   fmt = '%s - "%s %s HTTP/%s" %s'
        rec = _l.LogRecord("uvicorn.access", _l.INFO, "p", 1,
                           '%s - "%s %s HTTP/%s" %s', None, None)
        rec.args = ("127.0.0.1:5555", "GET",
                    f"/api/share/downloadFile?link={self.LINK}&ticket={self.TICKET}",
                    "1.1", 200)
        return rec

    def _run_filter(self, rec):
        from app.main import _AccessLogSecretFilter
        assert _AccessLogSecretFilter().filter(rec) is True
        return rec

    def test_redacts_link_and_ticket_with_real_uvicorn_formatter(self):
        try:
            from uvicorn.logging import AccessFormatter
        except Exception:
            import pytest as _p; _p.skip("uvicorn formatter unavailable")
        rec = self._run_filter(self._make_record(AccessFormatter))
        out = AccessFormatter().format(rec)  # must NOT raise
        assert self.LINK not in out and self.TICKET not in out
        assert "link=a1b2c3…" in out and "ticket=a1b2c3…" in out
        assert "200" in out  # status still logged (no dropped line)

    def test_formatter_survives_args_tuple_contract(self):
        # AccessFormatter unpacks exactly 5 args; filter must preserve shape.
        rec = self._run_filter(self._make_record(None))
        assert isinstance(rec.args, tuple) and len(rec.args) == 5

    def test_idempotent_double_filter(self):
        rec = self._make_record(None)
        once = self._run_filter(rec)
        before = once.args
        twice = self._run_filter(once)
        assert twice.args == before

    def test_plain_path_untouched(self):
        import logging as _l
        rec = _l.LogRecord("uvicorn.access", _l.INFO, "p", 1,
                           '%s - "%s %s HTTP/%s" %s', None, None)
        rec.args = ("1.2.3.4:5", "GET", "/api/files/list?parent_folder_uuid=abc", "1.1", 200)
        rec = self._run_filter(rec)
        assert rec.args[2] == "/api/files/list?parent_folder_uuid=abc"

    def test_percent_encoded_values_masked(self):
        import logging as _l
        rec = _l.LogRecord("uvicorn.access", _l.INFO, "p", 1,
                           '%s - "%s %s HTTP/%s" %s', None, None)
        rec.args = ("1.2.3.4:5", "GET",
                    "/api/files/download?file_uuid=u&token=" + "ab" * 32 + "%2E111",
                    "1.1", 200)
        rec = self._run_filter(rec)
        assert "ababab…" in rec.args[2] and "ab" * 32 not in rec.args[2]


class TestRedTeamRound10Fixes:
    """Locks for deep-pentest round: F2 cross-tenant, cookie dupes, depth,
    restore-parent, tus abort, ticket password-epoch."""

    def test_f2_resolve_rejects_foreign_base(self, db_session, sample_account, sample_home_folder):
        import uuid as _u
        from app.models.account import Account
        from app.models.folder import Folder
        from app.services.folder_service import FolderService
        other = Account(name="other99", password="x", email="o@x.cc", signal_file_size=10**8,
                        total_file_size=10**8, used_size=0, identity=0, enable=True)
        db_session.add(other); db_session.flush()
        of = Folder(uuid=str(_u.uuid4()), owner_id=other.id, parent_id=None, name="Home", size=0, is_system=True)
        db_session.add(of); db_session.commit()
        svc = FolderService(db_session)
        res = svc.resolve_or_create_path(sample_account.id, of.uuid, "evil")
        assert res.get("stateCode") in (403, 400), res

    def test_duplicate_session_cookie_rejected(self):
        from app.utils.session_auth import parse_session_cookie
        assert parse_session_cookie("session=1|a; session=2|b") is None
        assert parse_session_cookie("session=1|a") == "1|a"

    def test_depth_cap_blocks_65th_level(self, db_session, sample_account, sample_home_folder):
        from app.services.folder_service import FolderService
        svc = FolderService(db_session)
        parent = sample_home_folder.uuid
        for i in range(63):
            r = svc.create(sample_account.id, parent, f"L{i}")
            assert 'error' not in r, (i, r)
            parent = r['uuid']
        r = svc.create(sample_account.id, parent, "too-deep")
        assert r.get("stateCode") == 400, r

    def test_restore_file_into_trashed_parent_conflicts(self, db_session, sample_account, sample_home_folder, tmp_path, monkeypatch):
        import uuid as _u
        from datetime import datetime
        from app.models.file import File
        from app.models.folder import Folder
        from app.services.file_service import FileService
        monkeypatch.setattr("app.config.settings.STORAGE_BASE_PATH", str(tmp_path))
        sub = Folder(uuid=str(_u.uuid4()), owner_id=sample_account.id, parent_id=sample_home_folder.uuid, name="sub", size=0, deleted_at=datetime.utcnow())
        f = File(uuid=str(_u.uuid4()), owner_id=sample_account.id, parent_folder_id=sub.uuid, name="x.txt", size=1, mime_type="text/plain", storage_path="p", deleted_at=datetime.utcnow())
        db_session.add_all([sub, f]); db_session.commit()
        svc = FileService(db_session)
        r = svc.restore(sample_account.id, f.uuid)
        assert 'error' not in r, r
        db_session.refresh(sub)
        assert sub.deleted_at is None  # ancestor auto-restored, no orphan

    def test_rename_system_folder_forbidden(self, db_session, sample_account, sample_home_folder):
        from app.services.folder_service import FolderService
        svc = FolderService(db_session)
        r = svc.rename(sample_account.id, sample_home_folder.uuid, "Hacked")
        assert r.get("stateCode") == 403, r

    def test_tus_abort_owner_check(self, db_session, sample_account, sample_home_folder, tmp_path, monkeypatch):
        from app.services.file_service import FileService
        monkeypatch.setattr("app.config.settings.STORAGE_BASE_PATH", str(tmp_path))
        svc = FileService(db_session)
        r = svc.create_tus_upload(sample_account.id, sample_home_folder.uuid, "a.bin", 10)
        uid = r["upload_id"]
        bad = svc.abort_tus_upload(uid, sample_account.id + 999)
        assert bad.get("stateCode") == 404
        ok = svc.abort_tus_upload(uid, sample_account.id)
        assert ok.get("ok") is True
        import os
        assert not os.path.exists(os.path.join(str(tmp_path), "tus_uploads", uid))

    def test_ticket_invalidated_on_password_rotation(self):
        from app.utils.share_ticket import issue_ticket, verify_ticket
        t = issue_ticket("hash123", "argon-old-prefix")
        assert verify_ticket("hash123", t, "argon-old-prefix")
        assert not verify_ticket("hash123", t, "argon-NEW-prefix"), "rotating password must kill tickets"
        assert not verify_ticket("hash123", t), "no-marker verify must fail for marker'd ticket"


class TestRedTeamRound11Locks:
    """Locks for DS2 bypasses of round-10 fixes."""

    def test_cookie_whitespace_variant_parses(self):
        from app.utils.session_auth import parse_session_cookie
        assert parse_session_cookie("session = 1|abc") == "1|abc"
        assert parse_session_cookie("session= 1|abc") == "1|abc"
        assert parse_session_cookie("session=1|a; session=2|b") is None

    def test_ticket_marker_changes_with_password(self):
        from app.services.share_service import _pw_marker
        h1 = "$argon2id$v=19$m=65536,t=6,p=6$AAAA$hashone"
        h2 = "$argon2id$v=19$m=65536,t=6,p=6$BBBB$hashtwo"
        assert _pw_marker(h1) != _pw_marker(h2)
        assert _pw_marker("") != _pw_marker(h1)

    def test_unique_name_is_case_insensitive(self):
        from app.utils.pathing import unique_name
        assert unique_name("A.TXT", {"a.txt"}) != "A.TXT"

    def test_move_depth_guard_exists(self):
        import inspect
        from app.services.folder_service import FolderService
        src = inspect.getsource(FolderService.move_folders)
        assert "_subtree_height" in src and "MAX_FOLDER_DEPTH" in src

    def test_ancestor_chain_has_no_64_cut(self):
        import inspect
        from app.services.folder_service import FolderService
        src = inspect.getsource(FolderService._ancestor_uuids)
        assert "guard < 64" not in src

    def test_public_path_segment_budget(self):
        from app.utils.pathing import sanitize_rel_path
        deep = "/".join("s%d" % i for i in range(100))
        segs, err = sanitize_rel_path(deep)
        assert err is not None


class TestRedTeamRound12Locks:
    """Locks for DS3 findings: share path budgets, collab-cascade delete,
    restore collision healing, date/length validation."""

    def test_share_path_segment_cap(self):
        from app.services.share_service import ShareService
        deep = "/".join("s%d" % i for i in range(100))
        assert ShareService._split_public_path(deep) is None
        assert ShareService._split_public_path("a/b/c") == ["a", "b", "c"]

    def test_collect_total_budget_break(self):
        import inspect
        from app.services.share_service import ShareService
        src = inspect.getsource(ShareService.collect_shared_items)
        assert "budget" in src

    def test_hard_delete_clears_collaborations(self, db_session, sample_account, sample_home_folder, tmp_path, monkeypatch):
        import uuid as _u
        from app.models.file import File
        from app.models.collaboration import Collaboration
        from app.repositories.file_repository import FileRepository
        monkeypatch.setattr("app.config.settings.STORAGE_BASE_PATH", str(tmp_path))
        fu = str(_u.uuid4())
        db_session.add(File(uuid=fu, owner_id=sample_account.id, parent_folder_id=sample_home_folder.uuid,
                            name="collab.txt", size=1, mime_type="text/plain", storage_path="p"))
        db_session.add(Collaboration(file_uuid=fu, owner_id=sample_account.id, collaborator_id=110, permission="editor"))
        db_session.commit()
        repo = FileRepository(db_session)
        assert repo.hard_delete(fu) is True          # used to raise IntegrityError
        assert db_session.query(File).filter(File.uuid == fu).first() is None
        assert db_session.query(Collaboration).filter(Collaboration.file_uuid == fu).count() == 0

    def test_heal_name_conflict_renames(self, db_session, sample_account, sample_home_folder):
        import uuid as _u
        from app.models.folder import Folder
        from app.services.folder_service import FolderService
        live = Folder(uuid=str(_u.uuid4()), owner_id=sample_account.id, parent_id=sample_home_folder.uuid, name="Docs", size=0)
        ghost = Folder(uuid=str(_u.uuid4()), owner_id=sample_account.id, parent_id=sample_home_folder.uuid, name="Docs", size=0,
                       deleted_at=__import__("datetime").datetime.utcnow())
        db_session.add_all([live, ghost]); db_session.commit()
        svc = FolderService(db_session)
        new = svc._heal_name_conflict(ghost)
        assert new and new != "Docs"

    def test_getlink_bad_date_400_source(self):
        import inspect
        from app.api.v1 import share as sh
        src = inspect.getsource(sh)
        assert "到期日期格式不正確" in src

    def test_tus_bad_length_400_source(self):
        import inspect
        from app.api.v1 import files as fs
        src = inspect.getsource(fs)
        assert "except (TypeError, ValueError):" in src and "Invalid Upload-Length" in src


class TestWsDispatchBehavioral:
    """DS5 F5-1 lock: the viewer gate must not shadow the per-type handlers.
    Drives the REAL websocket_collab loop with a scripted fake socket and
    asserts dispatch side effects (behavior, not source strings)."""

    @staticmethod
    def _run(monkeypatch, role, msgs, fu="F" * 36, uid=109):
        import asyncio, types
        from app.api.v1 import collab_ws as cw
        from starlette.websockets import WebSocketDisconnect

        calls = {"persist": [], "append": [], "broadcast": [], "sent": [], "state": []}

        class FakeR:
            def getdel(self, k): return f"{uid}:{fu}"
            def get(self, k): return "x" if k.startswith("session:") else None
            def set(self, *a, **k): return True
            def setex(self, *a, **k): return True
            def delete(self, *a): return 1
            def expire(self, *a, **k): return True
            def close(self): pass
        monkeypatch.setattr(cw, "Redis", types.SimpleNamespace(from_url=lambda *a, **k: FakeR()))
        monkeypatch.setattr(cw, "_perm_ok", lambda *a, **k: True)
        monkeypatch.setattr(cw, "_perm_role_cached", lambda *a, **k: role)
        monkeypatch.setattr(cw, "_ensure_y_state_version", lambda *a: None)
        monkeypatch.setattr(cw, "_load_y_base_content", lambda *a: "ORIGINAL")
        monkeypatch.setattr(cw, "_get_y_updates", lambda *a, **k: [])
        monkeypatch.setattr(cw, "get_snapshots", lambda *a: [])
        monkeypatch.setattr(cw, "_snapshot_summary", lambda s: [])
        monkeypatch.setattr(cw, "_room_users", lambda f: [])
        monkeypatch.setattr(cw, "_get_y_state_key", lambda f: "yst")
        monkeypatch.setattr(cw, "_watch", lambda *a, **k: asyncio.sleep(3600))
        def _bc(f, msg, exclude=None):
            calls["broadcast"].append(msg["type"])
        async def _bc_a(f, msg, exclude=None): calls["broadcast"].append(msg.get("type"))
        monkeypatch.setattr(cw, "_broadcast", _bc_a)
        monkeypatch.setattr(cw, "_append_y_update", lambda f, r, u, cap: calls["append"].append(u) or True)
        monkeypatch.setattr(cw, "_has_y_updates", lambda f, r: False)
        monkeypatch.setattr(cw, "_set_collab_content", lambda f, r, c: (calls["state"].append(c), True)[1])
        monkeypatch.setattr(cw, "_set_y_state", lambda f, r, u: None)
        def _pc(file_uuid, content): calls["persist"].append(content); return True
        async def _pc_a(*a, **k): return True
        monkeypatch.setattr(cw, "persist_content", lambda f, c: calls["persist"].append(c) or True)

        class FakeWS:
            def __init__(self, script): self.script = list(script); self.sent = []
            @property
            def headers(self): return {}
            scope = {"subprotocols": [cw.WS_SUBPROTOCOL, "T" * 43]}
            async def accept(self, subprotocol=None): pass
            async def close(self, code=1000): pass
            async def receive_json(self):
                if not self.script: raise WebSocketDisconnect()
                await asyncio.sleep(0)
                return self.script.pop(0)
            async def send_json(self, obj): self.sent.append(obj); calls["sent"].append(obj)

        mgr = types.SimpleNamespace(count=lambda f: 0, add=lambda *a: None,
                                    remove=lambda *a: None, rooms={})
        monkeypatch.setattr(cw, "manager", mgr)
        ws = FakeWS(msgs)
        asyncio.run(cw.websocket_collab(ws, fu))
        return calls

    FU = "F" * 36

    def test_owner_persist_reaches_disk(self, monkeypatch):
        calls = self._run(monkeypatch, "owner",
                          [{"type": "persist_text", "content": "V2"}], self.FU)
        assert "V2" in calls["persist"], calls          # F5-1 regression lock
        assert not any(s.get("type") == "write_error" for s in calls["sent"])

    def test_editor_y_update_broadcasts(self, monkeypatch):
        calls = self._run(monkeypatch, "editor",
                          [{"type": "y_update", "update": "dXBk"}], self.FU)
        assert calls["append"], calls                   # appended
        assert "y_update" in calls["broadcast"]         # broadcast to peers

    def test_viewer_write_rejected_not_dispatched(self, monkeypatch):
        calls = self._run(monkeypatch, "viewer",
                          [{"type": "persist_text", "content": "X"}], self.FU)
        assert not calls["persist"]
        assert any(s.get("type") == "write_error" for s in calls["sent"])

    def test_none_role_closes(self, monkeypatch):
        calls = self._run(monkeypatch, None,
                          [{"type": "y_update", "update": "x"}], self.FU)
        assert not calls["append"]

    def test_unknown_type_falls_through_harmlessly(self, monkeypatch):
        calls = self._run(monkeypatch, "editor",
                          [{"type": "cursor", "cursor": {"i": 1}}], self.FU)
        assert not calls["persist"] and not calls["append"]


class TestRedTeamRound6Locks:
    """Locks for DS6 findings (F6-1/F6-2/F6-3)."""

    def test_f6_1_collab_edit_charges_owner(self, db_session, sample_account, sample_home_folder, tmp_path, monkeypatch):
        import uuid as _u
        from datetime import datetime
        from app.models.file import File
        from app.models.account import Account
        from app.models.collaboration import Collaboration
        from app.services.folder_service import FolderService
        monkeypatch.setattr("app.config.settings.STORAGE_BASE_PATH", str(tmp_path))
        collab = Account(name="editor99", password="x", email="e@x.cc", signal_file_size=10**8,
                         total_file_size=10**8, used_size=0, identity=0, enable=True,
                         email_verified_at=datetime.utcnow())
        db_session.add(collab); db_session.commit()
        f = File(uuid=str(_u.uuid4()), owner_id=sample_account.id,
                 parent_folder_id=sample_home_folder.uuid, name="s.txt",
                 size=5, mime_type="text/plain", storage_path="p")
        db_session.add(f)
        db_session.add(Collaboration(file_uuid=f.uuid, owner_id=sample_account.id,
                                     collaborator_id=collab.id, permission="editor"))
        db_session.commit()
        # write 105 bytes through the SAME persist path REST now shares semantics with
        import app.services.collab_persist as CP
        class _NoClose:
            def __init__(self, s): self._s = s
            def __getattr__(self, n): return getattr(self._s, n)
            def close(self): pass
        monkeypatch.setattr(CP, "SessionLocal", lambda: _NoClose(db_session))
        from app.services.collab_persist import persist_content
        ok = persist_content(f.uuid, "y" * 105)
        assert ok
        db_session.refresh(sample_account); db_session.refresh(collab)
        assert sample_account.used_size == 100   # owner charged by delta (+100), not absolute
        assert collab.used_size == 0             # collaborator untouched

    def test_f6_2_preview_raw_uses_role(self):
        import inspect
        from app.api.v1 import preview as P
        src = inspect.getsource(P)
        assert "_file_access_role" in src and "File.owner_id == uid" not in src

    def test_f6_3_unknown_role_fails_closed(self):
        import inspect
        from app.api.v1 import files as F, collab_ws as C
        assert '"editor", "viewer"' in inspect.getsource(F)
        assert '"editor", "viewer"' in inspect.getsource(C)


class TestSaveContentQuotaBehavioral:
    """DS7 F7-1 lock: save_file_content must compute size deltas UNDER the
    account+file locks and land quota exactly on real bytes. Self-contained
    app with a StaticPool sqlite shared across threads (serializes, like the
    real account-row lock does on MySQL)."""

    def _build(self, monkeypatch, tmp_path):
        import uuid as _u
        from datetime import datetime
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import MagicMock
        from app.models.base import Base
        import app.models.account, app.models.folder, app.models.file, app.models.collaboration  # noqa
        from app.models.account import Account
        from app.models.folder import Folder
        from app.models.file import File
        from app.api.v1 import files as F
        from app.api import dependencies as D
        from app.services.feature_flag_service import FeatureFlagService

        eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                            poolclass=StaticPool)
        Base.metadata.create_all(eng)
        S = sessionmaker(bind=eng, autoflush=False, expire_on_commit=False)
        db = S()
        owner = Account(name="own71", password="x", email="o7@x.cc", signal_file_size=10**8,
                        total_file_size=10**8, used_size=0, identity=0, enable=True,
                        email_verified_at=datetime.utcnow())
        db.add(owner); db.flush()
        home = Folder(uuid=str(_u.uuid4()), owner_id=owner.id, parent_id=None,
                      name="Home", size=0, is_system=True)
        db.add(home); db.flush()
        f = File(uuid=str(_u.uuid4()), owner_id=owner.id, parent_folder_id=home.uuid,
                 name="q.txt", size=0, mime_type="text/plain", storage_path="x")
        db.add(f); db.commit()
        self._oid, self._fid, self._dbfile = owner.id, f.uuid, db

        monkeypatch.setattr(F.settings, "STORAGE_BASE_PATH", str(tmp_path))
        monkeypatch.setattr(FeatureFlagService, "effective_enabled",
                            lambda self, key, default=False: True)
        def _gd():
            yield S()
        app = FastAPI()
        app.include_router(F.router)
        app.dependency_overrides[D.get_db] = _gd
        app.dependency_overrides[D.get_current_user_id] = lambda: owner.id
        rmock = MagicMock()
        rmock.pipeline.return_value.execute.return_value = [1, 500]
        rmock.smembers.return_value = set()
        rmock.get.return_value = None
        rmock.exists.return_value = 0
        rmock.set.return_value = True
        app.dependency_overrides[D.get_redis] = lambda: rmock
        return TestClient(app), S, tmp_path

    def test_sequential_and_interleaved_edits_keep_quota_equal_bytes(self, monkeypatch, tmp_path):
        import threading
        c, S, tmp_path = self._build(monkeypatch, tmp_path)
        fid = self._fid

        def used():
            d = S()
            try:
                from app.models.account import Account
                return d.query(Account.used_size).filter(Account.id == self._oid).scalar()
            finally:
                d.close()

        assert c.put("/api/files/content", json={"uuid": fid, "text": "A" * 500}).status_code == 200
        assert used() == 500
        assert c.put("/api/files/content", json={"uuid": fid, "text": "B" * 100}).status_code == 200
        assert used() == 100
        assert c.put("/api/files/content", json={"uuid": fid, "text": "C" * 900}).status_code == 200
        assert used() == 900

        def put(s):
            c.put("/api/files/content", json={"uuid": fid, "text": s * 300})
        ts = [threading.Thread(target=put, args=(ch,)) for ch in "XYZ"]
        [t.start() for t in ts]; [t.join() for t in ts]
        assert used() == 300                      # exactly one 300-byte file
        import os
        assert os.path.getsize(os.path.join(str(tmp_path), fid)) == 300
        self._dbfile.close()


class TestBatchPermanentQuotaR19:
    """R8 heredoc truncation regrew these locks; R19: account FOR UPDATE row
    kept and refunded from; sizes re-read current (post-lock) not snapshot."""

    def _perm_branch(self):
        src = open("app/services/batch_ops.py").read()
        return src.split('elif mode == "permanent":')[1].split('else:  # restore')[0]

    def test_account_locked_first_and_kept(self):
        b = self._perm_branch()
        assert b.index("Account.id == user_id)") < b.index("sa_delete(File)")
        assert "acct = (" in b and ".with_for_update()" in b
        assert "used_size = max(0, (acct.used_size or 0) - freed)" in b
        # plain snapshot re-read removed
        assert re.search(r"acct =\s*db\.query\(Account\)\.filter\(Account\.id == user_id\)\.first\(\)", b) is None

    def test_sizes_are_current_reads(self):
        b = self._perm_branch()
        assert "select(File.uuid, File.size)" in b
        assert "fresh_size" in b and "freed = sum(fresh_size.values())" in b
        # locking reads come after the account lock
        assert b.index("Account.id == user_id)") < b.index("select(File.uuid, File.size)")


class TestFolderTrashRevokeShareLock:
    def test_trash_clears_share_in_all_paths(self):
        fs = open("app/services/folder_service.py").read()
        bo = open("app/services/batch_ops.py").read()
        assert "child_folder.shared = None" in fs or "folder.shared = None" in fs
        assert "shared=None" in bo  # batch soft-delete clears hash atomically

    def test_share_access_denies_trashed_items(self):
        src = open("app/services/share_service.py").read()
        assert "_check_share_access" in src
        assert 'getattr(item, "deleted_at", None) is not None' in src
        assert src.count("deleted_at.is_(None)") >= 3


class TestTicketPwEpochLock:
    def test_ticket_marker_binds_password_epoch(self):
        st = open("app/utils/share_ticket.py").read()
        assert "def issue_ticket(share_hash: str, pwd_marker" in st
        assert "def verify_ticket(share_hash: str, ticket" in st
        assert "share_hash}|{pwd_marker" in st
        w = open("app/services/share_service.py").read()
        assert "_pw_marker" in w
        assert "verify_ticket(share_hash, ticket, _pw_marker" in w


class FakeCollabRedis:
    def __init__(self):
        self.kv = {}
        self._ttls = {}
        self.deleted = []
    def scan_iter(self, pattern):
        pfx = pattern.rstrip("*")
        return [k for k in self.kv if k.startswith(pfx)]
    def get(self, k):
        return self.kv.get(k)
    def ttl(self, k):
        return self._ttls.get(k, -2)
    def expire(self, k, s):
        if k in self.kv:
            self._ttls[k] = s
    def delete(self, k):
        if k in self.kv:
            self.deleted.append(k)
            del self.kv[k]
            self._ttls.pop(k, None)
            return 1
        return 0


class TestAutosaveRedisPinningR20:
    """R11-MED-1: autosaved/failed collab buffers must not pin Redis 7d."""

    def _seed(self, r, uuid="f"*20, content="x"*1000):
        r.kv[f"collab_content:{uuid}"] = content
        r._ttls[f"collab_content:{uuid}"] = 7*24*3600
        r.kv[f"collab_ystate:{uuid}"] = "b64blob"
        r._ttls[f"collab_ystate:{uuid}"] = 7*24*3600
        r.kv[f"collab_snapshot:{uuid}"] = '[{"id":1}]'
        r._ttls[f"collab_snapshot:{uuid}"] = 7*24*3600
        return uuid

    def test_success_and_empty_room_purges_volatile_keeps_snapshots(self, monkeypatch):
        from app.main import collab_autosave_tick
        import app.services.collab_persist as cp
        import app.api.v1.collab_ws as cw
        monkeypatch.setattr(cp, "persist_content", lambda u, c: True)
        r = FakeCollabRedis()
        u = self._seed(r)
        assert not cw.manager.rooms.get(u)
        collab_autosave_tick(r)
        assert f"collab_content:{u}" in r.deleted
        assert f"collab_ystate:{u}" in r.deleted
        assert f"collab_snapshot:{u}" not in r.deleted  # version archive survives

    def test_success_with_live_room_keeps_state(self, monkeypatch):
        from app.main import collab_autosave_tick
        import app.services.collab_persist as cp
        import app.api.v1.collab_ws as cw
        monkeypatch.setattr(cp, "persist_content", lambda u, c: True)
        r = FakeCollabRedis()
        u = self._seed(r)
        cw.manager.rooms[u] = {"conn": {"user_id": 1, "websocket": None}}
        try:
            collab_autosave_tick(r)
        finally:
            cw.manager.rooms.pop(u, None)
        assert f"collab_content:{u}" not in r.deleted
        assert r._ttls[f"collab_content:{u}"] == 7*24*3600

    def test_failure_demotes_ttl_once(self, monkeypatch):
        from app.main import collab_autosave_tick
        import app.services.collab_persist as cp
        monkeypatch.setattr(cp, "persist_content", lambda u, c: False)
        r = FakeCollabRedis()
        u = self._seed(r)
        collab_autosave_tick(r)
        assert f"collab_content:{u}" not in r.deleted
        assert r._ttls[f"collab_content:{u}"] == 3600
        ttl1 = r._ttls[f"collab_ystate:{u}"]
        collab_autosave_tick(r)  # next tick must not re-arm a sliding TTL
        assert r._ttls[f"collab_ystate:{u}"] == ttl1
        assert r._ttls[f"collab_snapshot:{u}"] == 7*24*3600

    def test_source_lock_scheduler_tick_contract(self):
        src = open("app/main.py").read()
        assert "def collab_autosave_tick" in src
        assert "include_snapshots=False" in src
        assert "demote_failed_state_ttl" in src
