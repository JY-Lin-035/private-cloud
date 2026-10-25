"""Round-2 regression tests: zero-byte uploads, empty-chunk append, verify lockout."""
import asyncio
import os

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import MagicMock

from app.constants import Identity
from app.models.base import Base
from app.models.account import Account
from app.models.folder import Folder


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, 'STORAGE_BASE_PATH', str(tmp_path / 'storage'))
    eng = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=eng)
    db = sessionmaker(bind=eng)()
    user = Account(name="u", password="p", email="u@x.io", identity=Identity.USER)
    user.id = 1
    home = Folder(uuid="home", name="Home", owner_id=1, parent_id=None, is_system=True, size=0)
    db.add_all([user, home]); db.commit()
    yield {"db": db, "tmp": tmp_path}
    db.close()


class TestZeroByteUpload:
    def test_create_and_finalize_empty_file(self, env):
        from app.services.file_service import FileService
        svc = FileService(env["db"])
        r = svc.create_tus_upload(1, "home", "UnLock.txt", 0)
        assert 'error' not in r
        fin = svc.finalize_tus_upload(r['upload_id'])
        assert 'error' not in fin, fin
        from app.models.file import File
        f = env["db"].query(File).filter(File.name == "UnLock.txt").first()
        assert f is not None and f.size == 0
        assert os.path.isfile(f.storage_path)

    def test_append_empty_chunk_is_noop_completed(self, env):
        from app.services.file_service import FileService
        svc = FileService(env["db"])
        r = svc.create_tus_upload(1, "home", "zero.bin", 0)
        res = svc.append_tus_chunk(r['upload_id'], 0, b'')
        assert 'error' not in res and res['completed'] is True and res['offset'] == 0

    def test_negative_length_rejected_at_endpoint(self, env):
        from app.api.v1 import files as files_api
        class Req:
            client = type('c', (), {'host': 'x'})()
            headers = {}
            async def body(self): return b''
            def url_for(self, *a, **k): return '/x'
        with pytest.raises(HTTPException) as exc:
            asyncio.run(files_api.tus_create_upload(
                request=Req(), upload_metadata='filename ' + __import__('base64').b64encode(b'a.txt').decode(),
                upload_length='-5', tus_resumable='1.0.0', x_parent_folder_uuid='', db=env["db"], user_id=1))
        assert exc.value.status_code == 400


class TestVerifyLockout:
    def _req(self, link='lk', password='pw'):
        from app.api.v1.share import ShareVerifyRequest
        return ShareVerifyRequest(link=link, password=password)

    def _http(self, ip='9.9.9.9'):
        r = MagicMock()
        r.client.host = ip
        return r

    def test_locked_out_after_10_failures(self, env):
        from app.api.v1.share import share_verify_password
        redis = MagicMock()
        redis.get.return_value = b'10'
        with pytest.raises(HTTPException) as exc:
            asyncio.run(share_verify_password(request=self._http(), body=self._req(), db=env["db"], redis_client=redis))
        assert exc.value.status_code == 429

    def test_wrong_password_increments_counter(self, env):
        from app.api.v1.share import share_verify_password
        from app.models.file import File
        from app.utils.security import hash_password
        f = File(uuid="fx", name="f", size=1, owner_id=1, parent_folder_id="home",
                 storage_path=str(env["tmp"] / "f"), shared="lk2", share_password=hash_password("right"))
        env["db"].add(f); env["db"].commit()
        redis = MagicMock()
        redis.get.return_value = None
        redis.incr.return_value = 1
        with pytest.raises(HTTPException) as exc:
            asyncio.run(share_verify_password(request=self._http(), body=self._req(link='lk2', password='bad'), db=env["db"], redis_client=redis))
        assert exc.value.status_code == 403
        redis.incr.assert_called_once_with('sharePwFail:lk2:9.9.9.9')
        redis.expire.assert_called_once_with('sharePwFail:lk2:9.9.9.9', 900)

    def test_success_clears_counter(self, env):
        from app.api.v1.share import share_verify_password
        from app.models.file import File
        from app.utils.security import hash_password
        f = File(uuid="fy", name="f", size=1, owner_id=1, parent_folder_id="home",
                 storage_path=str(env["tmp"] / "f"), shared="lk3", share_password=hash_password("right"))
        env["db"].add(f); env["db"].commit()
        redis = MagicMock()
        redis.get.return_value = '3'
        r = asyncio.run(share_verify_password(request=self._http(), body=self._req(link='lk3', password='right'), db=env["db"], redis_client=redis))
        assert 'ticket' in r
        redis.delete.assert_called_once_with('sharePwFail:lk3:9.9.9.9')


class TestItemsZipName:
    def test_part_suffix_and_sanitizing(self, env):
        from app.api.v1 import share as share_api
        from app.api.v1.share import ShareItemsRequest
        from app.models.file import File
        root = Folder(uuid="share-root", name="R", owner_id=1, parent_id="home", size=2, shared="lkz")
        f = File(uuid="fz", name="z.txt", size=2, owner_id=1, parent_folder_id="share-root",
                 storage_path=str(env["tmp"] / "z.txt"))
        (env["tmp"] / "z.txt").write_bytes(b"hi")
        env["db"].add_all([root, f]); env["db"].commit()
        req = ShareItemsRequest(link="lkz", paths=["z.txt"], folder_name='my/photos":x')
        resp = asyncio.run(share_api.share_download_items(request=req, db=env["db"]))
        cd = resp.headers['content-disposition']
        # forbidden chars stripped, suffix -part applied
        assert "myphotosx-part.zip" in cd
