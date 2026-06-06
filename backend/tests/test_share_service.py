"""Share service unit tests."""
import pytest

from app.services.share_service import ShareService
from app.constants import HTTPStatus


class TestShareGetList:

    def test_get_list_empty(self, db_session, sample_account):
        service = ShareService(db_session)
        result = service.get_list(sample_account.id)
        assert result is not None
        assert "list" in result


class TestShareCreateLink:

    def test_create_link_nonexistent_user(self, db_session):
        service = ShareService(db_session)
        result = service.create_link(99999, "fake-uuid", "file")
        assert result is not None
        assert result["stateCode"] == HTTPStatus.NOT_FOUND


class TestShareDownload:

    def test_download_nonexistent_hash(self,  db_session):
        service = ShareService(db_session)
        result = service.download("nonexistent-hash")
        assert result is not None
        assert "error" in result