
"""Private-Cloud Shared Test Fixtures"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.base import Base
from app.constants import StorageLimits, Identity, AccountDefaults
from app.models.account import Account
from app.models.folder import Folder
from app.models.file import File


@pytest.fixture
def db_session():
    """in-memory SQLite session"""
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def account_repo(db_session):
    from app.repositories.account_repository import AccountRepository
    return AccountRepository(db_session)


@pytest.fixture
def file_repo(db_session):
    from app.repositories.file_repository import FileRepository
    return FileRepository(db_session)


@pytest.fixture
def folder_repo(db_session):
    from app.repositories.folder_repository import FolderRepository
    return FolderRepository(db_session)


@pytest.fixture
def mock_redis(mocker):
    """mocked Redis client"""
    redis_mock = mocker.MagicMock()
    redis_mock.get.return_value = None
    redis_mock.set.return_value = True
    redis_mock.setex.return_value = True
    redis_mock.delete.return_value = True
    redis_mock.expire.return_value = True
    pipe = mocker.MagicMock()
    pipe.incr.return_value = pipe
    pipe.expire.return_value = pipe
    pipe.execute.return_value = [1]
    redis_mock.pipeline.return_value = pipe
    return redis_mock


@pytest.fixture
def sample_account(db_session):
    from app.models.account import Account
    from app.utils.security import hash_password
    account = Account(
        name = "testuser",
        password = hash_password("TestP@ssw0rd!@#"),
        email = "test@example.com",
        signal_file_size = StorageLimits.DEFAULT_SIGNAL_FILE_SIZE,
        total_file_size = StorageLimits.DEFAULT_TOTAL_FILE_SIZE,
        used_size = AccountDefaults.USED_SIZE,
        identity = Identity.USER,
        enable = True,
        email_verified_at = datetime.utcnow(),
    )
    db_session.add(account)
    db_session.commit()
    db_session.refresh(account)
    return account


@pytest.fixture
def sample_home_folder(db_session, sample_account):
    import uuid
    from app.models.folder import Folder
    folder = Folder(
        uuid = str(uuid.uuid4()),
        owner_id = sample_account.id,
        parent_id = None,
        name = "Home",
        size = 0,
        is_system = True,
    )
    db_session.add(folder)
    db_session.commit()
    db_session.refresh(folder)
    return folder


@pytest.fixture
def sample_file(db_session, sample_account, sample_home_folder):
    import uuid
    from app.models.file import File
    file = File(
        uuid = str(uuid.uuid4()),
        owner_id = sample_account.id,
        parent_folder_id = sample_home_folder.uuid,
        name = "test.txt",
        size = 1024,
        mime_type = "text/plain",
        storage_path = "/fake/path/test.txt"
    )
    db_session.add(file)
    db_session.commit()
    db_session.refresh(file)
    return file


def assert_success(resp: dict) -> None:
    """Helper: assert no 'error' in response"""
    assert "error" not in resp, f"Got: {resp.get('error')}"


def assert_error(resp: dict, code: int) -> None:
    """Helper: assert error response has expected status code"""
    assert "error" in resp
    assert resp["stateCode"] == code, f"{code} != {resp['stateCode']}"
