"""P1 preview backend: create / content read / content save — flag gates,
ownership isolation, quota + size-chain accounting, conflict and lock guards."""
import asyncio
import os
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import Identity
from app.models.base import Base
from app.models.account import Account
from app.models.folder import Folder
from app.models.file import File
from app.api.v1 import files
from app.api.v1 import settings as settings_api
from app.config import settings


class FakeR:
    def __init__(self):
        self.held = set()

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.held:
            return False
        self.held.add(k)
        return True

    def exists(self, k):
        return k in self.held

    def delete(self, k):
        self.held.discard(k)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    acct = Account(name="alice", email="a@x.io", password="p", identity=Identity.USER,
                   enable=True, used_size=0, total_file_size=100_000, signal_file_size=50_000)
    other = Account(name="bob", email="b@x.io", password="p", identity=Identity.USER,
                    enable=True, used_size=0, total_file_size=100_000, signal_file_size=50_000)
    db.add_all([acct, other]); db.flush()
    home = Folder(uuid="home-a", name="Home", owner_id=acct.id, parent_id=None, is_system=True, size=0)
    sub = Folder(uuid="sub-a", name="docs", owner_id=acct.id, parent_id="home-a", size=0)
    foreign = Folder(uuid="home-b", name="Home", owner_id=other.id, parent_id=None, is_system=True, size=0)
    db.add_all([home, sub, foreign]); db.commit()
    monkeypatch.setattr(settings, "STORAGE_BASE_PATH", str(tmp_path))
    monkeypatch.setattr(files, "is_feature_enabled", lambda k, default=True: True)
    yield db, acct, other, tmp_path
    db.close()


def _create(db, user, name, parent=None, r=None):
    return asyncio.run(files.create_text_file(
        request=files.CreateFileRequest(name=name, parent_folder_uuid=parent),
        db=db, redis=r or FakeR(), user_id=user.id))


def _get(db, user, uuid):
    return asyncio.run(files.get_file_content(uuid=uuid, db=db, user_id=user.id))


def _put(db, user, uuid, text, if_u=None, r=None):
    return asyncio.run(files.save_file_content(
        request=files.SaveContentRequest(uuid=uuid, text=text, if_updated_at=if_u),
        db=db, redis=r or FakeR(), user_id=user.id))


def _mkfile(db, owner, name, content=b"", parent="sub-a"):
    u = "f-" + name
    open(os.path.join(settings.STORAGE_BASE_PATH, u), "wb").write(content)
    row = File(uuid=u, owner_id=owner.id, parent_folder_id=parent, name=name,
               size=len(content), mime_type="text/plain",
               storage_path=f"storage/{u}", updated_at=datetime.utcnow())
    db.add(row); db.commit()
    return row


class TestFlagGate:
    def test_flag_off_blocks_all_three(self, ctx, monkeypatch):
        db, a, *_ = ctx
        monkeypatch.setattr(files, "is_feature_enabled", lambda k, default=True: False)
        for fn in (lambda: _create(db, a, "x.txt"),
                   lambda: _get(db, a, "whatever"),
                   lambda: _put(db, a, "whatever", "hi")):
            with pytest.raises(HTTPException) as ex:
                fn()
            assert ex.value.status_code == 403


class TestCreate:
    def test_create_ok_blob_and_row(self, ctx):
        db, a, *_ = ctx
        res = _create(db, a, "筆記 #1.md", "sub-a")
        assert res["category"] == "markdown" and res["size"] == 0
        assert os.path.isfile(os.path.join(str(ctx[4 - 1]), res["uuid"]))
        row = db.query(File).filter(File.uuid == res["uuid"]).first()
        assert row.owner_id == a.id and row.parent_folder_id == "sub-a"

    def test_rejects_binary_ext(self, ctx):
        db, a, *_ = ctx
        with pytest.raises(HTTPException) as ex:
            _create(db, a, "tool.exe")
        assert ex.value.status_code == 400

    def test_rejects_bad_name(self, ctx):
        db, a, *_ = ctx
        with pytest.raises(HTTPException) as ex:
            _create(db, a, ".hidden.txt")
        assert ex.value.status_code == 400

    def test_foreign_parent_404(self, ctx):
        db, a, *_ = ctx
        with pytest.raises(HTTPException) as ex:
            _create(db, a, "x.txt", "home-b")
        assert ex.value.status_code == 404

    def test_locked_parent_423(self, ctx):
        db, a, *_ = ctx
        r = FakeR()
        r.held.add("delLock:sub-a")
        with pytest.raises(HTTPException) as ex:
            _create(db, a, "x.txt", "sub-a", r=r)
        assert ex.value.status_code == 423

    def test_name_collision_renamed(self, ctx):
        db, a, *_ = ctx
        _mkfile(db, a, "dup.txt")
        res = _create(db, a, "dup.txt", "sub-a")
        assert res["name"] != "dup.txt"


class TestContent:
    def test_read_roundtrip(self, ctx):
        db, a, *_ = ctx
        _mkfile(db, a, "hello.py", "print('hi')".encode())
        got = _get(db, a, "f-hello.py")
        assert got["text"] == "print('hi')" and got["category"] == "code"

    def test_noneditable_404(self, ctx):
        db, a, *_ = ctx
        _mkfile(db, a, "photo.png", b"\x89PNG")
        with pytest.raises(HTTPException) as ex:
            _get(db, a, "f-photo.png")
        assert ex.value.status_code == 404

    def test_other_owner_404(self, ctx):
        db, a, b, *_ = ctx
        _mkfile(db, a, "mine.txt")
        with pytest.raises(HTTPException) as ex:
            _get(db, b, "f-mine.txt")
        assert ex.value.status_code == 404

    def test_trashed_404(self, ctx):
        db, a, *_ = ctx
        row = _mkfile(db, a, "gone.txt")
        row.deleted_at = datetime.utcnow(); db.commit()
        with pytest.raises(HTTPException) as ex:
            _get(db, a, "f-gone.txt")
        assert ex.value.status_code == 404

    def test_oversize_413(self, ctx):
        db, a, *_ = ctx
        row = _mkfile(db, a, "big.txt")
        row.size = 3 * 1024 * 1024; db.commit()
        with pytest.raises(HTTPException) as ex:
            _get(db, a, "f-big.txt")
        assert ex.value.status_code == 413


class TestSave:
    def test_write_and_accounting(self, ctx):
        db, a, *_ = ctx
        _mkfile(db, a, "acc.txt", b"12345")  # size 5, parent sub-a size 0
        res = _put(db, a, "f-acc.txt", "x" * 100)
        db.expire_all()
        assert res["size"] == 100
        assert db.query(File).filter(File.uuid == "f-acc.txt").first().size == 100
        assert db.query(Folder).filter(Folder.uuid == "sub-a").first().size == 95  # chain delta +95 (5->100)
        acct = db.query(Account).get(a.id)
        assert acct.used_size == 95  # delta only
        path = os.path.join(str(ctx[3]), "f-acc.txt")
        assert open(path, "rb").read() == b"x" * 100

    def test_shrink(self, ctx):
        db, a, *_ = ctx
        _mkfile(db, a, "shr.txt", b"y" * 200)
        q=db.query(Account).filter(Account.id==a.id).first(); q.used_size=200; db.commit()
        _put(db, a, "f-shr.txt", "z")
        db.expire_all()
        assert db.query(Account).filter(Account.id == a.id).first().used_size == 1
        assert db.query(Folder).filter(Folder.uuid == "sub-a").first().size == 0  # 鏈由 0 起扣，max(0) 護欄

    def test_conflict_409(self, ctx):
        db, a, *_ = ctx
        _mkfile(db, a, "race.txt")
        with pytest.raises(HTTPException) as ex:
            _put(db, a, "f-race.txt", "hi", if_u="1999-01-01T00:00:00")
        assert ex.value.status_code == 409

    def test_quota_exceeded_413(self, ctx):
        db, a, *_ = ctx
        a.total_file_size = 10
        _mkfile(db, a, "q.txt")
        db.commit()
        with pytest.raises(HTTPException) as ex:
            _put(db, a, "f-q.txt", "x" * 500)
        assert ex.value.status_code == 413
        assert db.query(File).filter(File.uuid=="f-q.txt").first().size == 0  # unchanged

    def test_single_file_limit_413(self, ctx):
        db, a, *_ = ctx
        a.signal_file_size = 10
        _mkfile(db, a, "s.txt")
        db.commit()
        with pytest.raises(HTTPException) as ex:
            _put(db, a, "f-s.txt", "x" * 100)
        assert ex.value.status_code == 413

    def test_locked_423(self, ctx):
        db, a, *_ = ctx
        _mkfile(db, a, "lk.txt")
        r = FakeR(); r.held.add("delLock:f-lk.txt")
        with pytest.raises(HTTPException) as ex:
            _put(db, a, "f-lk.txt", "hi", r=r)
        assert ex.value.status_code == 423

    def test_save_updates_mtime_token(self, ctx):
        db, a, *_ = ctx
        _mkfile(db, a, "mt.txt")
        r1 = _put(db, a, "f-mt.txt", "v1")
        r2 = _put(db, a, "f-mt.txt", "v22", if_u=r1["updated_at"])
        assert r2["updated_at"] != r1["updated_at"]


class TestAuthedFlags:
    def test_endpoint_shape_and_gate(self, ctx, monkeypatch):
        from app.models.feature_flag import FeatureFlag
        from app.constants import HTTPStatus
        db, a, *_ = ctx
        db.add_all([
            FeatureFlag(key="enable_file_preview", enabled=True),
        ]); db.commit()
        req = type("R", (), {"state": type("S", (), {"user": {"id": 1}})})()
        out = asyncio.run(settings_api.authed_settings(request=req, db=db))
        assert out == {"enable_file_preview": True}
        anon = type("R", (), {"state": type("S", (), {})})()
        with pytest.raises(HTTPException) as ex:
            asyncio.run(settings_api.authed_settings(request=anon, db=db))
        assert ex.value.status_code == 401


async def _collect(resp):
    return b"".join([c if isinstance(c, bytes) else c.encode() async for c in resp.body_iterator])


def _mkmedia(ctx, name="clip.mp4", content=b"A" * 1000):
    db, a, *_ = ctx
    row = File(uuid="f-media", owner_id=a.id, parent_folder_id=None, name=name,
               size=len(content), mime_type="video/mp4", storage_path="storage/f-media")
    db.add(row); db.commit()
    open(os.path.join(settings.STORAGE_BASE_PATH, "f-media"), "wb").write(content)
    return content


class _Req:
    def __init__(self, headers=None):
        self.headers = headers or {}
        self.client = type("C", (), {"host": "9.9.9.9"})()
        self.state = type("S", (), {"user": {"username": "alice"}})()


class TestStream:
    def test_basics_headers(self, ctx):
        db, a, *_ = ctx
        _mkmedia(ctx)
        resp = asyncio.run(files.stream_file(uuid="f-media", request=_Req(), db=db,
                                             redis=FakeR(), user_id=a.id))
        assert resp.status_code == 200
        h = {k.lower(): v for k, v in resp.headers.items()}
        assert h["accept-ranges"] == "bytes"
        assert h["content-length"] == "1000"
        assert h["x-content-type-options"] == "nosniff"
        assert "no-store" in h["cache-control"]
        assert "default-src 'none'" in h["content-security-policy"]
        assert asyncio.run(_collect(resp)) == b"A" * 1000

    def test_range_slices(self, ctx):
        db, a, *_ = ctx
        _mkmedia(ctx)
        r1 = asyncio.run(files.stream_file(uuid="f-media", request=_Req({"range": "bytes=100-199"}),
                                           db=db, redis=FakeR(), user_id=a.id))
        assert r1.status_code == 206
        assert asyncio.run(_collect(r1)) == b"A" * 100
        assert r1.headers["content-range"] == "bytes 100-199/1000"
        r2 = asyncio.run(files.stream_file(uuid="f-media", request=_Req({"range": "bytes=-50"}),
                                           db=db, redis=FakeR(), user_id=a.id))
        assert r2.headers["content-range"] == "bytes 950-999/1000"
        r3 = asyncio.run(files.stream_file(uuid="f-media", request=_Req({"range": "bytes=990-"}),
                                           db=db, redis=FakeR(), user_id=a.id))
        assert len(asyncio.run(_collect(r3))) == 10

    def test_range_invalid_416(self, ctx):
        db, a, *_ = ctx
        _mkmedia(ctx)
        for bad in ("bytes=1000-2000", "bytes=", "bytes=200-100"):
            with pytest.raises(HTTPException) as ex:
                asyncio.run(files.stream_file(uuid="f-media", request=_Req({"range": bad}),
                                              db=db, redis=FakeR(), user_id=a.id))
            assert ex.value.status_code == 416, bad

    def test_cross_user_and_nonmedia_404(self, ctx):
        db, a, b, *_ = ctx
        _mkmedia(ctx)
        with pytest.raises(HTTPException) as ex:
            asyncio.run(files.stream_file(uuid="f-media", request=_Req(), db=db, redis=FakeR(), user_id=b.id))
        assert ex.value.status_code == 404
        html = File(uuid="f-html", owner_id=a.id, parent_folder_id=None, name="x.html",
                    size=5, mime_type="text/html", storage_path="storage/f-html")
        db.add(html); db.commit()
        with pytest.raises(HTTPException) as ex2:
            asyncio.run(files.stream_file(uuid="f-html", request=_Req(), db=db, redis=FakeR(), user_id=a.id))
        assert ex2.value.status_code == 404

    def test_locked_423(self, ctx):
        db, a, *_ = ctx
        _mkmedia(ctx)
        r = FakeR(); r.held.add("delLock:f-media")
        with pytest.raises(HTTPException) as ex:
            asyncio.run(files.stream_file(uuid="f-media", request=_Req(), db=db, redis=r, user_id=a.id))
        assert ex.value.status_code == 423

    def test_flag_off_403(self, ctx, monkeypatch):
        db, a, *_ = ctx
        _mkmedia(ctx)
        monkeypatch.setattr(files, "is_feature_enabled", lambda k, default=True: False)
        with pytest.raises(HTTPException) as ex:
            asyncio.run(files.stream_file(uuid="f-media", request=_Req(), db=db, redis=FakeR(), user_id=a.id))
        assert ex.value.status_code == 403


class TestSaveEdge:
    def test_same_size_edit_bumps_mtime(self, ctx):
        db, a, *_ = ctx
        _mkfile(db, a, "same.txt", b"AA")
        r1 = _put(db, a, "f-same.txt", "BB")
        r2 = _put(db, a, "f-same.txt", "CC", if_u=r1["updated_at"])
        assert r2["updated_at"] != r1["updated_at"]
        with pytest.raises(HTTPException) as ex:
            _put(db, a, "f-same.txt", "DD", if_u=r1["updated_at"])
        assert ex.value.status_code == 409
