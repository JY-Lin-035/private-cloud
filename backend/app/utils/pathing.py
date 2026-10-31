"""Shared path helpers for nested uploads and moves."""
from typing import Optional

from app.utils.name_validation import validate_display_name

MAX_PATH_DEPTH = 16


def sanitize_rel_path(rel_path: str) -> tuple[list[str], Optional[str]]:
    """Split a user-supplied relative path into safe segments.

    Returns (segments, error). Rejects traversal attempts, names failing the
    shared display-name denylist, and excessive depth; empty segments dropped.
    """
    if rel_path is None:
        return [], '缺少路徑'
    raw = rel_path.replace('\\', '/').strip('/')
    if not raw:
        return [], None
    segments = []
    for part in raw.split('/'):
        if len(segments) >= 64:
            return [], '路徑層級過多'
        part = part.strip()
        if not part:
            continue
        if part in ('.', '..'):
            return [], '路徑包含不合法段落'
        cleaned, error = validate_display_name(part)
        if error:
            return [], f'名稱不合法: {part[:30]}'
        segments.append(cleaned)
    if len(segments) > MAX_PATH_DEPTH:
        return [], f'路徑深度超過上限 {MAX_PATH_DEPTH}'
    return segments, None


def unique_name(base: str, taken: set[str]) -> str:
    """Return base or 'name (1).ext' style increments absent from taken.

    Comparison is case-insensitive (NFC+casefold) because MySQL's default
    collation treats 'A.txt' and 'a.txt' as equal; case-sensitive checks here
    allowed CI-duplicate rows that later blow up as 500s (red-team F3/DS2-6).
    """
    taken_ci = {t.casefold() for t in taken}
    if base.casefold() not in taken_ci:
        return base
    if '.' in base and not base.startswith('.'):
        stem, dot, ext = base.rpartition('.')
    else:
        stem, dot, ext = base, '', ''
    i = 1
    while True:
        candidate = f"{stem} ({i}){dot}{ext}" if dot else f"{stem} ({i})"
        if candidate.casefold() not in taken_ci:
            return candidate
        i += 1
