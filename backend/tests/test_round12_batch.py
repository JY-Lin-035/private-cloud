"""Round 12: batch trash ops — subtree semantics, locks (423), accounting, idempotency."""
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
import app.database as database
from app.services import batch_ops
from app.config import settings


class FakeR:
    def __init__(self):
        self.held = {}

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.held:
            return False
        self.held[k] = v
        return True

    def exists(self, k):
        return k in self.held

    def delete(self, k):
        self.held.pop(k, None)


@pytest.fixture
def env(tmp_path, monkeypatch):
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    S = sessionmaker(bind=eng)
    monkeypatch.setattr(database, "SessionLocal", S)
    monkeypatch.setattr(settings, "STORAGE_BASE_PATH", str(tmp_path))
    db = S()
    a = Account(name="u1", email="u@x.io", password="p", identity=Identity.USER, enable=True,
                used_size=0, total_file_size=10**9, signal_file_size=10**9)
    db.add(a); db.flush()
    home = Folder(uuid="home-1", name="Home", owner_id=a.id, parent_id=None, is_system=True, size=0)
    db.add(home); db.flush()
    yield db, a, home, S, tmp_path
    db.close()


def _mkfolder(db, uuid, parent, name, owner, size=0):
    f = Folder(uuid=uuid, name=name, owner_id=owner, parent_id=parent, size=size)
    db.add(f); db.flush(); return f

def _mkfile(db, uuid, parent, name, owner, size, blob=False, deleted=False):
    f = File(uuid=uuid, name=name, owner_id=owner, parent_folder_id=parent, size=size,
             mime_type="text/plain", storage_path=f"storage/{uuid}",
             deleted_at=datetime.utcnow() if deleted else None)
    db.add(f); db.flush()
    if blob:
        (os.path.join(str(settings.STORAGE_BASE_PATH), uuid)).__class__  # noop
        open(os.path.join(str(settings.STORAGE_BASE_PATH), uuid), "wb").write(b"x" * size)
    return f


class TestSoftBatch:
    def test_folder_subtree_soft_and_unshare(self, env):
        db, a, home, S, tmp = env
        f1 = _mkfolder(db, "F1", home.uuid, "一", a.id)
        f2 = _mkfolder(db, "F2", "F1", "二", a.id)
        _mkfile(db, "A", "F1", "a.txt", a.id, 10); fl2 = _mkfile(db, "B", "F2", "b.txt", a.id, 20)
        fl2.shared = "tok-live"
        db.commit()
        r = FakeR()
        res = batch_ops.batch_operation(a.id, ["F1"], [], "soft", r)
        assert res["folders"] == 2 and res["files"] == 2
        db.expire_all()
        assert all(x.deleted_at for x in db.query(Folder).filter(Folder.uuid.in_(["F1", "F2"])))
        assert db.query(File).filter(File.uuid == "B").first().deleted_at is not None
        assert db.query(File).filter(File.uuid == "B").first().shared is None
        assert not r.held  # locks released

    def test_lock_conflict_423_and_release_on_fail(self, env):
        db, a, home, S, tmp = env
        _mkfolder(db, "F1", home.uuid, "x", a.id); db.commit()
        r = FakeR()
        r.held[batch_ops._k("F1")] = "1"  # another tab mid-delete
        with pytest.raises(HTTPException) as ex:
            batch_ops.batch_operation(a.id, ["F1"], [], "soft", r)
        assert ex.value.status_code == 423
        assert "F1" in [k.split(":")[1] for k in r.held]  # pre-existing lock survived

    def test_idempotent_second_run(self, env):
        db, a, home, S, tmp = env
        _mkfile(db, "A", None, "a.txt", a.id, 5); db.commit()
        r = FakeR()
        b1 = batch_ops.batch_operation(a.id, [], ["A"], "soft", r)
        b2 = batch_ops.batch_operation(a.id, [], ["A"], "soft", r)
        assert b1["files"] == 1 and b2["files"] == 0 and b2["skipped"]


class TestPermanentBatch:
    def test_accounting_chain_and_blobs(self, env):
        db, a, home, S, tmp = env
        f1 = _mkfolder(db, "F1", home.uuid, "keep", a.id, size=30)
        _mkfile(db, "A", "F1", "a.txt", a.id, 10, blob=True)
        _mkfile(db, "B", "F1", "b.txt", a.id, 20, blob=True)
        a.used_size = 30
        db.commit()
        r = FakeR()
        res = batch_ops.batch_operation(a.id, [], ["A"], "permanent", r)
        db.expire_all()
        assert res["freed_bytes"] == 10
        assert db.query(File).filter(File.uuid == "A").first() is None
        assert not os.path.exists(os.path.join(str(tmp), "A"))
        assert os.path.exists(os.path.join(str(tmp), "B"))
        assert a.used_size == 20
        assert db.query(Folder).filter(Folder.uuid == "F1").first().size == 20

    def test_permanent_folder_whole_subtree(self, env):
        db, a, home, S, tmp = env
        _mkfolder(db, "F1", home.uuid, "x", a.id, size=30)
        _mkfolder(db, "F2", "F1", "y", a.id, size=20)
        _mkfile(db, "B", "F2", "b.txt", a.id, 20, blob=True)
        a.used_size = 30
        db.commit()
        r = FakeR()
        res = batch_ops.batch_operation(a.id, ["F1"], [], "permanent", r)
        db.expire_all()
        assert res["folders"] == 2 and res["files"] == 1 and res["freed_bytes"] == 20
        assert db.query(Folder).count() == 1  # only Home left
        assert a.used_size == 10
        assert not os.path.exists(os.path.join(str(tmp), "B"))

    def test_system_folder_protected(self, env):
        db, a, home, S, tmp = env
        r = FakeR()
        res = batch_ops.batch_operation(a.id, [home.uuid], [], "permanent", r)
        assert res["folders"] == 0 and res["skipped"][0]["reason"] == "系統資料夾無法刪除"


class TestRestoreBatch:
    def test_restore_renames_conflicts(self, env):
        db, a, home, S, tmp = env
        _mkfile(db, "A", None, "dup.txt", a.id, 5, deleted=True)
        _mkfile(db, "LIVE", None, "dup.txt", a.id, 1)
        db.commit()
        r = FakeR()
        res = batch_ops.batch_operation(a.id, [], ["A"], "restore", r)
        db.expire_all()
        a_row = db.query(File).filter(File.uuid == "A").first()
        assert a_row.deleted_at is None and a_row.name != "dup.txt"
        assert res["files"] == 1

    def test_restore_only_trashed_children(self, env):
        db, a, home, S, tmp = env
        _mkfolder(db, "F1", home.uuid, "x", a.id, size=10)
        # F1 trashed (with child marked), but CHILD was trashed BEFORE F1 individually —
        # batch restore must bring the whole recorded subtree of deleted rows back
        f1 = db.query(Folder).filter(Folder.uuid == "F1").first()
        f1.deleted_at = datetime.utcnow()
        _mkfile(db, "C", "F1", "c.txt", a.id, 10, deleted=True)
        db.commit()
        r = FakeR()
        res = batch_ops.batch_operation(a.id, ["F1"], [], "restore", r)
        db.expire_all()
        assert res["files"] == 1 and res["folders"] == 1
        assert db.query(File).filter(File.uuid == "C").first().deleted_at is None
        assert db.query(Folder).filter(Folder.uuid == "F1").first().deleted_at is None


class TestGuards:
    def test_assert_not_deleting_raises(self):
        r = FakeR()
        r.held[batch_ops._k("X")] = "1"
        with pytest.raises(HTTPException) as ex:
            batch_ops.assert_not_deleting(r, "OK1", "X")
        assert ex.value.status_code == 423

    def test_mixed_batch_partial_overlap_423(self, env):
        db, a, home, S, tmp = env
        _mkfile(db, "P", None, "p.txt", a.id, 1)
        _mkfile(db, "Q", None, "q.txt", a.id, 1)
        db.commit()
        r = FakeR()
        r.held[batch_ops._k("Q")] = "1"
        with pytest.raises(HTTPException) as ex:
            batch_ops.batch_operation(a.id, [], ["P", "Q"], "soft", r)
        assert ex.value.status_code == 423
        db.expire_all()
        assert db.query(File).filter(File.uuid == "P").first().deleted_at is None  # nothing applied
        assert batch_ops._k("P") not in r.held  # rolled back our lock, kept theirs
