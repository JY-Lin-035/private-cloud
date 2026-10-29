"""P3/P4: sandboxed raw preview — token auth (single-use), CSP posture, gates."""
import asyncio
import os
from datetime import datetime

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models.file import File
from app.api.v1 import preview
from tests.test_round13_preview_p1 import ctx  # noqa: F401  (fixture reuse)


class _R:
    def __init__(self):
        self.held = set()
        self.kv = {}

    def set(self, k, v, nx=False, ex=None):
        if nx and k in self.held:
            return False
        self.held.add(k)
        self.kv[k] = v.encode() if isinstance(v, str) else v
        return True

    def exists(self, k):
        return k in self.held

    def delete(self, k):
        self.held.discard(k)
        self.kv.pop(k, None)

    def setex(self, k, t, v):
        self.kv[k] = v.encode() if isinstance(v, str) else v
        self.held.add(k)

    def get(self, k):
        return self.kv.get(k)

    def getdel(self, k):
        v = self.kv.pop(k, None)
        self.held.discard(k)
        return v

    def expire(self, *a, **k): pass

    def pipeline(self):
        outer = self

        class P:
            def sadd(self, *a): pass
            def expire(self, *a): pass
            def execute(self): return []
        return P()


class _Req:
    def __init__(self, headers=None):
        self.headers = headers or {}


def _mkfile(db, owner, tmp, name, content):
    fu = "raw-" + name
    open(os.path.join(str(tmp), fu), "wb").write(content)
    f = File(uuid=fu, owner_id=owner.id, parent_folder_id=None, name=name,
             size=len(content), mime_type="text/html", storage_path=f"storage/{fu}",
             updated_at=datetime.utcnow())
    db.add(f)
    db.commit()
    return fu


def _token(db, r, uid, uuid):
    return asyncio.run(preview.issue_preview_token(
        request=preview.PreviewTokenRequest(uuid=uuid),
        http_request=_Req(), db=db, redis=r, user_id=uid)).get("token")


class TestRawSandbox:
    def test_token_flow_single_use_and_headers(self, ctx, monkeypatch):
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        u = _mkfile(db, a, ctx[3], "evil.html", b"<script>alert(1)</script>")
        r = _R()
        tk = _token(db, r, a.id, u)
        resp = asyncio.run(preview.preview_raw(uuid=u, ptk=tk, db=db, redis=r))
        assert resp.status_code == 200
        h = {k.lower(): v for k, v in resp.headers.items()}
        assert "sandbox" in h["content-security-policy"]
        assert h["x-content-type-options"] == "nosniff"
        assert b"alert(1)" in resp.body
        # single-use: second redemption fails
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.preview_raw(uuid=u, ptk=tk, db=db, redis=r))
        assert ex.value.status_code == 401

    def test_bad_token_401(self, ctx, monkeypatch):
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.preview_raw(uuid="whatever", ptk="nope", db=db, redis=_R()))
        assert ex.value.status_code == 401

    def test_token_bound_to_uuid(self, ctx, monkeypatch):
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        u1 = _mkfile(db, a, ctx[3], "a.html", b"<b>a</b>")
        u2 = _mkfile(db, a, ctx[3], "b.html", b"<b>b</b>")
        r = _R()
        tk = _token(db, r, a.id, u1)
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.preview_raw(uuid=u2, ptk=tk, db=db, redis=r))
        assert ex.value.status_code == 403

    def test_non_sandbox_ext_404(self, ctx, monkeypatch):
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        with pytest.raises(HTTPException) as ex:
            _token(db, _R(), a.id, "ghost")
        assert ex.value.status_code == 404

    def test_flag_off_403(self, ctx, monkeypatch):
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: False)
        with pytest.raises(HTTPException) as ex:
            _token(db, _R(), a.id, "x")
        assert ex.value.status_code == 403

    def test_untrusted_origin_403(self, ctx, monkeypatch):
        db, a, *_ = ctx
        monkeypatch.setattr(preview, "is_feature_enabled", lambda k, default=True: True)
        u = _mkfile(db, a, ctx[3], "ok.html", b"<b>ok</b>")
        with pytest.raises(HTTPException) as ex:
            asyncio.run(preview.issue_preview_token(
                request=preview.PreviewTokenRequest(uuid=u),
                http_request=_Req({"origin": "https://evil.example"}),
                db=db, redis=_R(), user_id=a.id))
        assert ex.value.status_code == 403
