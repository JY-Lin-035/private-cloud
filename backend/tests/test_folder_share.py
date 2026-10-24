"""Tests for public folder sharing: browse, full zip, selected items (M3)."""
import asyncio
import io
import zipfile
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import Identity
from app.models.base import Base
from app.models.account import Account
from app.models.file import File
from app.models.folder import Folder
from app.services.share_service import ShareService


@pytest.fixture
def env(tmp_path):
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    user = Account(name="sharer", password="p", email="s@x.io", identity=Identity.USER)
    user.id = 1
    root = Folder(uuid="SH", name="SharedRoot", owner_id=1, parent_id=None, size=13, shared="linkhash1")
    inner = Folder(uuid="IN", name="in", owner_id=1, parent_id="SH", size=3)
    ft = File(uuid="ft", name="top.txt", size=10, owner_id=1, parent_folder_id="SH",
              storage_path=str(tmp_path / "top.txt"))
    fd = File(uuid="fd", name="deep.txt", size=3, owner_id=1, parent_folder_id="IN",
              storage_path=str(tmp_path / "deep.txt"))
    (tmp_path / "top.txt").write_bytes(b"TOPDATA")
    (tmp_path / "deep.txt").write_bytes(b"DEEP")
    db.add_all([user, root, inner, ft, fd])
    db.commit()
    yield {"db": db, "tmp": tmp_path}
    db.close()


def svc(env):
    return ShareService(env["db"])


class TestBrowse:
    def test_root_listing(self, env):
        r = svc(env).browse("linkhash1", "", None)
        assert r["stateCode"] == 200
        assert [f["name"] for f in r["files"]] == ["top.txt"]
        assert [f["name"] for f in r["folders"]] == ["in"]
        assert "uuid" not in str(r)  # no internal uuids leaked

    def test_subpath(self, env):
        r = svc(env).browse("linkhash1", "in", None)
        assert [f["name"] for f in r["files"]] == ["deep.txt"]

    def test_traversal_rejected(self, env):
        r = svc(env).browse("linkhash1", "../..", None)
        assert r["stateCode"] in (400, 404)

    def test_missing_link_404(self, env):
        assert svc(env).browse("ghost", "", None)["stateCode"] == 404

    def test_password_gate_428(self, env):
        root = env["db"].query(Folder).filter(Folder.uuid == "SH").first()
        from app.utils.security import hash_password
        root.share_password = hash_password("pw123")
        env["db"].commit()
        assert svc(env).browse("linkhash1", "", None)["stateCode"] == 428
        ticket = svc(env).verify_share_password("linkhash1", "pw123")["ticket"]
        assert svc(env).browse("linkhash1", "", ticket)["stateCode"] == 200

    def test_expired_link_blocked(self, env):
        root = env["db"].query(Folder).filter(Folder.uuid == "SH").first()
        root.limited_date = datetime.utcnow() + timedelta(hours=8) - timedelta(days=1)
        env["db"].commit()
        assert svc(env).browse("linkhash1", "", None)["stateCode"] == 403


class TestSelectedDownload:
    def _zip_bytes(self, env, paths):
        from app.services import zip_service
        owner, fu, du, err = svc(env).collect_shared_items("linkhash1", paths, None)
        assert err is None
        items, _, _ = zip_service.collect_zip_items(env["db"], owner, fu, du)
        return b"".join(zip_service.zip_bytes_iter(items))

    def test_selected_mixed(self, env):
        blob = self._zip_bytes(env, ["top.txt", "in"])
        zf = zipfile.ZipFile(io.BytesIO(blob))
        names = set(zf.namelist())
        assert "top.txt" in names and "in/deep.txt" in names
        assert zf.read("in/deep.txt") == b"DEEP"

    def test_bad_path_falls_back_404(self, env):
        _, _, _, err = svc(env).collect_shared_items("linkhash1", ["../../etc/passwd"], None)
        assert err["stateCode"] == 404

    def test_full_folder_via_downloadItems_shape(self, env):
        from app.api.v1.share import share_browse
        r = asyncio.run(share_browse(link="linkhash1", sub="", ticket=None, db=env["db"]))
        assert set(r.keys()) == {"name", "folders", "files"}


class TestDownloadFolderHandler:
    def test_zip_stream_content(self, env):
        from app.api.v1.share import share_download_folder

        async def consume():
            resp = await share_download_folder(link="linkhash1", ticket=None, db=env["db"])
            chunks = [c.encode() if isinstance(c, str) else c async for c in resp.body_iterator]
            return b"".join(chunks)

        blob = asyncio.run(consume())
        zf = zipfile.ZipFile(io.BytesIO(blob))
        assert set(zf.namelist()) == {"SharedRoot/top.txt", "SharedRoot/in/deep.txt"}
        assert zf.read("SharedRoot/top.txt") == b"TOPDATA"

    def test_requires_ticket_when_protected(self, env):
        from app.api.v1.share import share_download_folder
        root = env["db"].query(Folder).filter(Folder.uuid == "SH").first()
        from app.utils.security import hash_password
        root.share_password = hash_password("secret")
        env["db"].commit()
        with pytest.raises(HTTPException) as exc:
            asyncio.run(share_download_folder(link="linkhash1", ticket=None, db=env["db"]))
        assert exc.value.status_code == 428
