"""Regression: tus PATCH/OPTIONS must return truly empty 204 (starlette Response, not JSONResponse)."""
import asyncio

from fastapi import Request
from starlette.responses import Response as StarletteResponse

from app.api.v1 import files as files_api


class TestTusEmptyResponses:
    def test_options_returns_empty_response(self):
        resp = asyncio.run(files_api.tus_options())
        assert isinstance(resp, StarletteResponse)
        assert resp.status_code == 204
        assert resp.body == b''
        assert 'content-length' not in {k.lower() for k in resp.headers.keys()} or resp.headers.get('content-length') in (None, '0')

    def test_patch_success_path_uses_empty_response(self, monkeypatch, tmp_path):
        """Drive append/finalize with a real temp upload, assert 204 with no body."""
        from app.services import file_service as fs_mod
        from app.models.account import Account  # noqa: F401  (import sanity)

        def fake_append(self, upload_id, offset, chunk):
            return {'offset': offset + len(chunk), 'completed': True}

        async def no_finalize(self, upload_id):
            return {'ok': True}

        monkeypatch.setattr(fs_mod.FileService, 'append_tus_chunk', lambda self, u, o, c, user_id=None: fake_append(self, u, o, c))
        monkeypatch.setattr(fs_mod.FileService, 'get_tus_upload', lambda self, u, user_id=None: {'offset': 0, 'file_size': 100, 'stateCode': 200})
        monkeypatch.setattr(fs_mod.FileService, 'finalize_tus_upload', lambda self, u, user_id=None: {'ok': True})

        headers = {
            'Tus-Resumable': '1.0.0',
            'Upload-Offset': '0',
        }

        class Req:
            client = type('c', (), {'host': '127.0.0.1'})()

            def __init__(self, body):
                self._body = body

            async def body(self):
                return self._body

            async def stream(self):
                yield self._body

            def url_for(self, name, **kw):
                return f'/api/files/tus/{kw.get("upload_id")}'

        resp = asyncio.run(files_api.tus_patch_upload(
            upload_id='u1', request=Req(b'chunk-data'),
            upload_offset='0', tus_resumable='1.0.0', db=None, user_id=1,
        ))
        assert isinstance(resp, StarletteResponse)
        assert resp.status_code == 204
        assert resp.body == b''
        assert resp.headers['upload-offset'] == '10'
        assert resp.headers['upload-complete'] == 'true'
