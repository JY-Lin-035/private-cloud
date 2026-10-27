"""Round 10 UX fixes: name denylist, path sanitize parity, session no-renew."""
from types import SimpleNamespace

from app.utils.name_validation import validate_display_name, MAX_NAME_LENGTH
from app.utils.pathing import sanitize_rel_path
from app.middleware.session_middleware import SessionMiddleware


class TestNameDenylist:

    def test_symbols_spaces_emoji_now_allowed(self):
        for name in ['Report (final) 2026', '專案 #42 – draft', 'emo 🎉 tag', 'a&b@c!$d^%', "it's.me"]:
            cleaned, err = validate_display_name(name)
            assert err is None, (name, err)
            assert cleaned == name.strip()

    def test_long_names_up_to_limit(self):
        assert validate_display_name('x' * MAX_NAME_LENGTH)[1] is None
        assert validate_display_name('x' * (MAX_NAME_LENGTH + 1))[1] is not None

    def test_dangerous_names_rejected(self):
        for name in ['../../etc/passwd', 'has/slash', 'back\\slash', '<script>alert(1)</script>',
                     'colon:here', 'q?mark', 'star*here', 'pipe|char', '"quoted"', 'endswithdot.',
                     '.hidden', '..', '.', '   ', '']:
            assert validate_display_name(name)[0] is None, name

    def test_bidi_and_control_invisible_rejected(self):
        assert validate_display_name('safe\u202eevil')[0] is None
        assert validate_display_name('nul\x00byte')[0] is None

    def test_whitespace_stripped_and_nfc(self):
        cleaned, err = validate_display_name('  筆記 本  ')
        assert err is None
        assert cleaned == '筆記 本'


class TestSanitizeParity:

    def test_symbolic_folder_tree_ok(self):
        segs, err = sanitize_rel_path('A (1)/b#2/c-3.0.txt')
        assert err is None
        assert segs == ['A (1)', 'b#2', 'c-3.0.txt']

    def test_hidden_segment_rejected(self):
        assert sanitize_rel_path('ok/.git')[1] is not None

    def test_overlong_segment_rejected(self):
        assert sanitize_rel_path('x' * 300)[1] is not None


class _MW:
    _is_no_renew = SessionMiddleware._is_no_renew
    NO_RENEW_PATHS = SessionMiddleware.NO_RENEW_PATHS


def _req(method: str, path: str):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path))


class TestSessionNoRenew:

    def test_get_announcements_is_no_renew(self):
        mw = _MW()
        assert mw._is_no_renew(_req('GET', '/api/announcements')) is True

    def test_admin_crud_still_renews(self):
        mw = _MW()
        assert mw._is_no_renew(_req('POST', '/api/announcements/admin/create')) is False
        assert mw._is_no_renew(_req('PUT', '/api/announcements/admin/1')) is False

    def test_real_operations_renew(self):
        mw = _MW()
        for path in ['/api/files/getList', '/api/folders/create', '/api/accounts/checkSession']:
            assert mw._is_no_renew(_req('POST', path)) is False
        assert mw._is_no_renew(_req('GET', '/api/files/getList')) is False
