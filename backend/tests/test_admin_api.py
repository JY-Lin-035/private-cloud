"""Tests for admin API endpoints (_admin_required function)."""

import pytest
from app.constants import Identity


class TestAdminRequired:
    """Test the _admin_required dependency function."""

    def test_no_user_state_returns_401(self):
            from app.api.v1.accounts import _admin_required
            from fastapi import HTTPException

            class MockReq:
                pass
            r = MockReq()
            # Don't set state.user at all -> hasattr fails -> 401
            r.state = object()
            with pytest.raises(HTTPException) as e:
                _admin_required(r)
            assert e.value.status_code == 401

    def test_non_admin_returns_403(self):
        from app.api.v1.accounts import _admin_required
        from fastapi import HTTPException

        class MockReq:
            pass
        r = MockReq()
        setattr(r, "state", type("", (), {"user": {"identity": Identity.USER}})())
        with pytest.raises(HTTPException) as e:
            _admin_required(r)
        assert e.value.status_code == 403

    def test_admin_succeeds(self):
        from app.api.v1.accounts import _admin_required

        class MockReq:
            pass
        r = MockReq()
        setattr(r, "state", type("", (), {"user": {"identity": Identity.ADMIN}})())
        result = _admin_required(r)
        assert result == {"identity": Identity.ADMIN}
