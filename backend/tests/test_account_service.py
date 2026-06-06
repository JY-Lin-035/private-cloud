"""Account service unit tests."""
import pytest
from unittest.mock import MagicMock, patch

from app.services.account_service import AccountService
from app.constants import HTTPStatus


class TestAccountRegister:

    def test_register_success(self, db_session, mock_redis):
        service = AccountService(db_session, mock_redis)
        result = service.register("newuser", "new@test.com",  "TestP@ssw0rd!@#")
        assert result is None

    def test_register_duplicate_username(self, db_session, mock_redis, sample_account):
        service = AccountService(db_session, mock_redis)
        result = service.register("testuser", "other@test.com", "TestP@ssw0rd!@#")
        assert result is not None
        assert "error" in result
        assert result["stateCode"] == HTTPStatus.CONFLICT

    def test_register_duplicate_email(self, db_session, mock_redis, sample_account):
        service = AccountService(db_session, mock_redis)
        result = service.register("other", "test@example.com",  "TestP@ssw0rd!@#")
        assert result is not None
        assert result["stateCode"] == HTTPStatus.CONFLICT


class TestAccountLogin:

    def test_login_success(self, db_session, mock_redis,  sample_account):
        service = AccountService(db_session, mock_redis)
        result = service.login("testuser", "TestP@ssw0rd!@#")
        assert result is not None
        assert "token" in result
        assert result["stateCode"] == HTTPStatus.OK

    def test_login_wrong_password(self, db_session, mock_redis, sample_account):
        service = AccountService(db_session, mock_redis)
        result = service.login("testuser", "wrongpass123!")
        assert result is not None
        assert "error" in result
        assert result["stateCode"] == HTTPStatus.UNAUTHORIZED

    def test_login_nonexistent_user(self, db_session, mock_redis):
        service = AccountService(db_session, mock_redis)
        result = service.login("nobody", "password")
        assert result is not None
        assert result["stateCode"] == HTTPStatus.UNAUTHORIZED


class TestAccountSignOut:

    def test_sign_out_success(self, db_session, mock_redis, sample_account):
        service = AccountService(db_session, mock_redis)
        result = service.sign_out(sample_account.id)
        assert result is None  # None means success
        mock_redis.delete.assert_called()


class TestAccountModifyEmail:

    def test_modify_email_nonexistent_user(self, db_session, mock_redis):
        service = AccountService(db_session, mock_redis)
        result = service.modify_email(99999, "new@test.com", "test@example.com", "code123")
        assert result is not None
        assert result["stateCode"] == HTTPStatus.NOT_FOUND


class TestAccountResetPassword:

    def test_reset_password_nonexistent_email(self, db_session, mock_redis):
        service = AccountService(db_session, mock_redis)
        result = service.reset_password("no@no.com", "code", "NewPass123!@#",)
        assert result is not None
        assert result["stateCode"] == HTTPStatus.NOT_FOUND


class TestAccountVerifyEmail:

    def test_verify_email_nonexistent_user(self, db_session, mock_redis):
        service = AccountService(db_session, mock_redis)
        result = service.verify_email(99999, "hash", "sig")
        assert result is not None
        assert result["stateCode"] == HTTPStatus.NOT_FOUND