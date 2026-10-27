"""Shared display-name validation for files and folders.

Whitelist was retired in favor of a denylist: names may contain spaces,
punctuation, symbols and emoji. Anything that could break path handling,
leak into Windows-invalid territory, spoof bidirectional text, or hide files
is rejected at the edge instead.
"""
import re
import unicodedata
from typing import Optional, Tuple

MAX_NAME_LENGTH = 255
MIN_NAME_LENGTH = 1

_FORBIDDEN_CHARS = re.compile(
    r'[\x00-\x1f\x7f<>"|?*/\\:'                      # control + path/Windows-invalid
    r'\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]'  # zero-width / bidi trojans
)


def validate_display_name(name: object) -> Tuple[Optional[str], Optional[str]]:
    """Return (cleaned_name, error). exactly one of the two is set."""
    if not isinstance(name, str) or name == '':
        return None, '名稱不可為空'
    cleaned = name.strip()
    if not cleaned:
        return None, '名稱不可僅為空白字元'
    if len(cleaned) > MAX_NAME_LENGTH:
        return None, f'名稱不可超過 {MAX_NAME_LENGTH} 字元'
    match = _FORBIDDEN_CHARS.search(cleaned)
    if match:
        return None, '名稱包含不允許的字元'
    if cleaned in ('.', '..') or cleaned.startswith('.'):
        return None, '名稱不可為隱藏檔格式（以 . 開頭）'
    if cleaned.endswith('.'):
        return None, '名稱不可使用 . 結尾'
    cleaned = unicodedata.normalize('NFC', cleaned)
    if len(cleaned) < MIN_NAME_LENGTH:
        return None, '名稱不可為空'
    return cleaned, None
