"""Repository layer unit tests."""
import pytest
from app.models.account import Account


class TestAccountRepository:

    def test_get_by_name(self, account_repo, sample_account):
        found = account_repo.get_by_name("testuser")
        assert found is not None
        assert found.id == sample_account.id

    def test_get_by_name_not_found(self, account_repo):
        assert account_repo.get_by_name("nonexistent") is None

    def test_name_exists(self, account_repo, sample_account):
        assert account_repo.name_exists("testuser") is True
        assert account_repo.name_exists("nobody") is False

    def test_email_exists(self, account_repo, sample_account):
        assert account_repo.email_exists("test@example.com")  is True
        assert account_repo.email_exists("no@no.com") is False


class TestFolderRepository:

    def test_get_by_uuid(self, folder_repo, sample_home_folder):
        found = folder_repo.get_by_uuid(sample_home_folder.uuid)
        assert found is not None
        assert found.name == "Home"

    def test_get_by_owner(self, folder_repo, sample_account, sample_home_folder):
        folders = folder_repo.get_by_owner(sample_account.id)
        assert len(folders) >= 1

    def test_get_home_folder(self, folder_repo, sample_account, sample_home_folder):
        home = folder_repo.get_home_folder(sample_account.id)
        assert home is not None
        assert home.name == "Home"

    def test_get_folder_path(self, folder_repo, sample_home_folder):
        path = folder_repo.get_folder_path(sample_home_folder.uuid)
        assert len(path) == 1
        assert path[0]["name"] == "Home"

    def test_hard_delete(self, folder_repo, sample_home_folder):
        folder_repo.hard_delete(sample_home_folder.uuid)
        assert folder_repo.get_by_uuid(sample_home_folder.uuid) is None


class TestFileRepository:    

    def test_get_by_uuid(self, file_repo, sample_file):
        found = file_repo.get_by_uuid(sample_file.uuid)
        assert found is not None

    def test_get_by_owner(self, file_repo, sample_account, sample_file):
        files = file_repo.get_by_owner(sample_account.id)
        assert len(files) == 1

    def test_get_by_folder(self, file_repo, sample_home_folder, sample_file):
        files = file_repo.get_by_folder(sample_home_folder.uuid)
        assert len(files) == 1

    def test_hard_delete(self, file_repo, sample_file):
        file_repo.hard_delete(sample_file.uuid)
        assert file_repo.get_by_uuid(sample_file.uuid) is None


class TestBaseRepository:

    def test_create(self, db_session):
        from app.repositories.base_repository import BaseRepository
        repo = BaseRepository(Account, db_session)
        user = Account(name="newuser", password="x", email="new@x.com")
        created = repo.create(user)
        assert created.id is not None
