"""Folder service unit tests."""
import pytest

from app.services.folder_service import FolderService
from app.constants import HTTPStatus


class TestFolderCreate:

    def test_create_nonexistent_user(self,  db_session):
        service = FolderService(db_session)
        result = service.create(99999, None, "TestFolder")
        assert result is not None
        assert result["stateCode"] == HTTPStatus.NOT_FOUND

    def test_create_invalid_name(self, db_session, sample_account):
        service = FolderService(db_session)
        result = service.create(sample_account.id, None, "")
        assert result is not None
        assert "error" in result


class TestFolderRename:

    def test_rename_nonexistent_folder(self, db_session, sample_account):
        service = FolderService(db_session)
        result = service.rename(sample_account.id, "fake-uuid", "NewName")
        assert result is not None
        assert  "error" in result