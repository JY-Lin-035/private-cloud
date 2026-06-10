"Utils layer unit tests."
from unittest.mock import Mock

from app.utils.security import hash_password, verify_password
from app.utils.security import generate_session_token, verify_session_token_format
from app.utils.security import hash_token
from app.utils.security import generate_signed_url, verify_signed_url
from app.utils.security import generate_verification_code
from app.utils.email_utils import format_email, mask_email
from app.utils.file_utils import format_file_size


class TestPasswordHashing:
    def test_hash(self):
        h = hash_password("TestP@ssw0rd!@#")
        assert len(h) > 0

    def test_hash_salted(self):
        pw = "TestP@ssw0rd!@#!"
        assert hash_password(pw) != hash_password(pw)

    def test_verify_ok(self):
        h = hash_password("TestP@ssw0rd!@#!@#")
        assert verify_password("TestP@ssw0rd!@#!@#", h)

    def test_verify_fail(self):
        h = hash_password("testP@ssw0rd!@#!@")
        assert not verify_password("wrong", h)


class TestSessionToken:
    def test_format(self):
        t = generate_session_token(42)
        assert t.split("|")[0] == "42" and len(t.split("|")) == 2

    def test_verify_ok(self):
        assert verify_session_token_format("1|x") is True

    def test_verify_fail(self):
        assert verify_session_token_format("abc") is False


class TestSignedUrl:
    def test_generate(self):
        r = generate_signed_url(1, "a@b.co")
        assert len(r) == 4

    def test_verify_no_redis(self):
        m = Mock()
        m.get.return_value = None
        r = verify_signed_url(1, "h", "s", m)
        assert r is False


class TestVerificationCode:
    def test_len(self):
        code = generate_verification_code()
        assert len(code) == 8

    def test_len_custom(self):
        assert len(generate_verification_code(6)) == 6


class TestHashToken:

    def test_hash_consistency(self):
        t = "42|abc123"
        h1 = hash_token(t)
        h2 = hash_token(t)
        assert h1 == h2
        assert len(h1) > 0

    def test_hash_different(self):
        h1 = hash_token("token1")
        h2 = hash_token("token2")
        assert h1 != h2


class TestEmailUtils:
    def test_format(self,):
        assert format_email("Test@Example.com") == "test@example.com"

    def test_mask(self):
        result = mask_email("testuser@example.com")
        assert result == "t*****r@example.com"


class TestFileSize:
    def test_zero(self):
        v, u = format_file_size(0)
        assert (v, u) == (0.0, "B")

    def test_kb(self):
        v, u = format_file_size(2048)
        assert abs(v - 2.0) < 0.01
        assert u == "KB"

    def test_target_unit(self):
        v, _ = format_file_size(1048576, "MB")
        assert abs(v - 1.0) < 0.01

    def test_invalid_unit(self):
        v, _ = format_file_size(1024, "XX")
        assert abs(v - 1024.0) < 0.01