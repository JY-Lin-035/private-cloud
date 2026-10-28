"""P3: sandboxed raw preview (token auth) + office convert guards."""
import asyncio
import os
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models.file import File
from app.api.v1 import preview
from tests.test_round13_preview_p1 import FakeR, ctx  # reuse fixtures


def _mkfile(tmp, uuid, name, content=b"x"):
    open(os.path.join(str(tmp), uuid), "wb").write(content)
    return uuid


def _sess(redis, uid, uuid):
    token = "tk-" + uuid[:6]
    redis.setex(f"pv:{token}", 600, f"{uid}|{uuid}")
    return token


class _R(FakeR):
    def __init__(self):
        super().__init__()
        self.kv = {}
    def expire(self, *a, **k): pass
    def setex(self, k, t, v):
        self.kv[k] = v.encode() if isinstance(v, str) else v
        self.held.add(k)
    def get(self, k):
        v = self.kv.get(k)
        return v if k not in ("conv:active",) else v

    def incr(self, k):
        self.kv[k] = int(self.kv.get(k, b"0")) + 1
        return self.kv[k]
    def decr(self, k):
        self.kv[k] = max(0, int(self.kv.get(k, b"0")) - 1)
        return self.kv[k]
    def pipeline(self):
        r = self
        class P:
            def sadd(self, *a): pass
            def expire(self, *a): pass
            def execute(self): return []
        return P()


class TestRawSandbox:
    def _file(self, db, a, tmp, name, content):
        u = "raw-" + name
        _mkfile(tmp, u, name, content)
        db.add(File(uuid=u, owner_id=a.id, parent_folder_id=None, name=name,
                    size=len(content), mime_type="text/html", storage_path=f"storage/{u}",
                    updated_at=datetime.utcnow()))
        db.commit()
        return u

    def test_token_flow_and_headers(self, ctx, monkeypatch):
        db, a, *_ = ctx
        tmp = ctx[3]
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        u = self._file(db, a, tmp, "evil.html", b"<script>alert(1)</script>")
        r = _R()
        res = asyncio.run(preview.issue_preview_token(
            request=preview.PreviewTokenRequest(uuid=u), db=db, redis=r, user_id=a.id))
        tok = res["token"]
        resp = asyncio.run(preview.preview_raw(uuid=u, ptk=tok, db=db, redis=r))
        assert resp.status_code == 200
        h = {k.lower(): v for k, v in resp.headers.items()}
        assert "sandbox" in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff"
        assert "no-store" in h["cache-control"]
        assert b"alert(1)" in resp.body

    def test_no_token_401(self, ctx, monkeypatch):
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.preview_raw(uuid="whatever", ptk="nope", db=db, redis=_R()))
        assert ex.value.status_code == 401

    def test_token_bound_to_uuid(self, ctx, monkeypatch):
        db, a, *_ = ctx
        tmp = ctx[3]
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        u = self._file(db, a, tmp, "p.html", b"<b>hi</b>")
        r = _R()
        tok = _sess(r, a.id, u)
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.preview_raw(uuid="other-uuid", ptk=tok, db=db, redis=r))
        assert ex.value.status_code == 403

    def test_non_sandbox_ext_rejected(self, ctx, monkeypatch):
        db, a, *_ = ctx
        tmp = ctx[3]
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.issue_preview_token(
                request=preview.PreviewTokenRequest(uuid="nope"), db=db, redis=_R(), user_id=a.id))
        assert ex.value.status_code == 404

    def test_flag_off(self, ctx, monkeypatch):
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: False)
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.issue_preview_token(
                request=preview.PreviewTokenRequest(uuid="x"), db=db, redis=_R(), user_id=a.id))
        assert ex.value.status_code == 403


class TestConvertGuards:
    def _office(self, db, a, tmp, name, content=b"PK\x03\x04fake"):
        u = "off-" + name
        _mkfile(tmp, u, name, content)
        db.add(File(uuid=u, owner_id=a.id, parent_folder_id=None, name=name,
                    size=len(content), mime_type="application/vnd.ms-powerpoint",
                    storage_path=f"storage/{u}", updated_at=datetime.utcnow()))
        db.commit()
        return u

    def test_flag_gate(self, ctx, monkeypatch):
        db, a, *_ = ctx
        calls = {"office": False}
        monkeypatch.setattr(preview, "is_feature_enabled",
                            lambda k, default=True: True if k == "enable_file_preview" else calls["office"])
        u = self._office(db, a, ctx[3], "deck.pptx")
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.convert_office(uuid=u, db=db, redis=_R(), user_id=a.id))
        assert ex.value.status_code == 403
        calls["office"] = True
        with pytest.raises(HTTPException) as ex2:
            asyncio.run(preview.convert_office(uuid="ghost", db=db, redis=_R(), user_id=a.id))
        assert ex2.value.status_code == 404

    def test_macro_rejected(self, ctx, monkeypatch):
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        u = self._office(db, a, ctx[3], "boom.docm")
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.convert_office(uuid=u, db=db, redis=_R(), user_id=a.id))
        assert ex.value.status_code == 415

    def test_no_binary_501(self, ctx, monkeypatch, tmp_path):
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        monkeypatch.setattr(preview, "_soffice_bin", lambda: None)
        u = self._office(db, a, ctx[3], "slides.odp")
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.convert_office(uuid=u, db=db, redis=_R(), user_id=a.id))
        assert ex.value.status_code == 501

    def test_convert_pipeline_with_stub(self, ctx, monkeypatch):
        """Full pipeline: soffice stub produces PDF -> cached -> served inline."""
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        monkeypatch.setattr(preview, "_soffice_bin", lambda: "stub")
        def fake_run(bin_path, src, out_dir, prof):
            open(os.path.join(out_dir, "stub.pdf"), "wb").write(b"%PDF-1.4 stub")
            return True
        monkeypatch.setattr(preview, "_run_convert", fake_run)
        u = self._office(db, a, ctx[3], "report.pptx")
        resp = asyncio.run(preview.convert_office(uuid=u, db=db, redis=_R(), user_id=a.id))
        assert resp.status_code == 200
        # cached file exists & second call skips conversion (stub would fail if called again without file)
        assert resp.path and os.path.isfile(resp.path)
        monkeypatch.setattr(preview, "_run_convert", lambda *x: False)
        resp2 = asyncio.run(preview.convert_office(uuid=u, db=db, redis=_R(), user_id=a.id))
        assert resp2.status_code == 200  # served from cache
