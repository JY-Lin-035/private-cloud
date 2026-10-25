"""Tests for folder upload paths, moves and bulk zip (M2)."""
import io
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import Identity
from app.models.base import Base
from app.models.account import Account
from app.models.file import File
from app.models.folder import Folder
from app.services.folder_service import FolderService
from app.services.file_service import FileService
from app.services import zip_service
from app.utils.pathing import sanitize_rel_path, unique_name


@pytest.fixture
def env(tmp_path):
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    user = Account(name="u", password="p", email="u@x.io", identity=Identity.USER)
    user.id = 1
    home = Folder(uuid="home", name="Home", owner_id=1, parent_id=None, size=0, is_system=True)
    a = Folder(uuid="A", name="a", owner_id=1, parent_id="home", size=100)
    b = Folder(uuid="B", name="b", owner_id=1, parent_id="A", size=100)
    f1 = File(uuid="f1", name="x.txt", size=100, owner_id=1, parent_folder_id="B",
              storage_path=str(tmp_path / "f1"))
    f2 = File(uuid="f2", name="x.txt", size=5, owner_id=1, parent_folder_id="home",
              storage_path=str(tmp_path / "f2"))
    (tmp_path / "f1").write_bytes(b"HELLO-F1")
    (tmp_path / "f2").write_bytes(b"HELLO-F2")
    db.add_all([user, home, a, b, f1, f2])
    db.commit()
    yield {"db": db, "tmp": tmp_path}
    db.close()


class TestSanitize:
    def test_traversal_rejected(self):
        _, err = sanitize_rel_path("ok/../../etc")
        assert err

    def test_empty_segments_dropped(self):
        segs, err = sanitize_rel_path("a//b/")
        assert err is None and segs == ["a", "b"]

    def test_depth_limit(self):
        _, err = sanitize_rel_path("/".join(f"d{i}" for i in range(20)))
        assert err

    def test_unique_name_keeps_extension(self):
        assert unique_name("x.txt", {"x.txt", "x (1).txt"}) == "x (2).txt"
        assert unique_name("noext", set()) == "noext"


class TestResolveOrCreatePath:
    def test_creates_chain_and_reuses(self, env):
        svc = FolderService(env["db"])
        r1 = svc.resolve_or_create_path(1, "home", "p/q")
        assert 'error' not in r1 and r1['created'] == ['p', 'q']
        r2 = svc.resolve_or_create_path(1, "home", "p/q")
        assert r2['uuid'] == r1['uuid'] and r2['created'] == []

    def test_base_none_uses_home(self, env):
        svc = FolderService(env["db"])
        r = svc.resolve_or_create_path(1, None, "z")
        z = env["db"].get(Folder, env["db"].query(Folder).filter(Folder.name == "z").first().id)
        assert z.parent_id == "home"


class TestMoveFiles:
    def test_move_with_auto_rename_and_sizes(self, env):
        svc = FileService(env["db"])
        r = svc.move_files(1, ["f2"], "B")  # f2 x.txt -> B already has x.txt(f1)
        assert r['moved'] == ['f2'] and r['renamed'] == {'x.txt': 'x (1).txt'}
        f2 = env["db"].query(File).filter(File.uuid == "f2").first()
        assert f2.parent_folder_id == "B" and f2.name == "x (1).txt"
        # size chains: B +5 up the chain; home clamps at 0 then +5 (fixture home starts 0)
        sizes = {f.uuid: f.size for f in env["db"].query(Folder).all()}
        assert sizes['home'] == 5 and sizes['A'] == 105 and sizes['B'] == 105

    def test_foreign_file_fails(self, env):
        other = File(uuid="f9", name="o", size=1, owner_id=2, parent_folder_id=None, storage_path="x")
        env["db"].add(other); env["db"].commit()
        r = FileService(env["db"]).move_files(1, ["f9"], "A")
        assert r['moved'] == [] and len(r['failed']) == 1


class TestMoveFolders:
    def test_cycle_rejected(self, env):
        r = FolderService(env["db"]).move_folders(1, ["A"], "B")
        assert r['moved'] == []
        assert "無法移動到自身或其子資料夾" in r['failed'][0]['reason']

    def test_move_adjusts_sizes(self, env):
        c = Folder(uuid="C", name="c", owner_id=1, parent_id="home", size=0)
        env["db"].add(c); env["db"].commit()
        r = FolderService(env["db"]).move_folders(1, ["A"], "C")
        assert r['moved'] == ['A']
        sizes = {f.uuid: f.size for f in env["db"].query(Folder).all()}
        assert sizes['A'] == 100 and sizes['C'] == 100
        assert env["db"].query(Folder).filter(Folder.uuid == "A").first().parent_id == "C"


class TestZip:
    def test_collect_dedups_covered_selection(self, env):
        items, kept_files, kept_folders = zip_service.collect_zip_items(
            env["db"], 1, ["f1"], ["A", "B"])
        arcs = sorted(a for _, a in items)
        assert kept_files == 0 and kept_folders == 1  # f1 and B are covered by A
        assert arcs == ["a/b/x.txt"]

    def test_stream_is_valid_zip_with_content(self, env):
        items, _, _ = zip_service.collect_zip_items(env["db"], 1, ["f1", "f2"], [])
        blob = b"".join(zip_service.zip_bytes_iter(items))
        zf = zipfile.ZipFile(io.BytesIO(blob))
        # both files are named x.txt at zip root -> second auto-renamed
        assert sorted(zf.namelist()) == sorted(["x.txt", "x (1).txt"])
        assert b"HELLO" in zf.read("x.txt") and b"HELLO" in zf.read("x (1).txt")

    def test_foreign_items_excluded(self, env):
        items, _, _ = zip_service.collect_zip_items(env["db"], 2, ["f1"], ["A"])
        assert items == []
