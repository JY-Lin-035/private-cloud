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
