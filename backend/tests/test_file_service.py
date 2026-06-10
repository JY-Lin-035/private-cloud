"""File service unit tests."""
import pytest

from app.services.file_service import FileService
from app.constants import HTTPStatus


class TestFileGetStorage:

    def test_get_storage_nonexistent_user(self, db_session):
        service = FileService(db_session)
        result = service.get_storage(99999)
        assert result is not None
        assert result["stateCode"] == HTTPStatus.NOT_FOUND

    def test_get_storage_success(self, db_session, sample_account):
            service = FileService(db_session)
            result = service.get_storage(sample_account.id)
            assert result is not None
            assert "used_storage" in result


class TestFileGetFileList:

    def test_get_file_list_empty(self, db_session, sample_account):
        service = FileService(db_session)
        result = service.get_file_list(sample_account.id)
        assert result is not None
        assert "files" in result