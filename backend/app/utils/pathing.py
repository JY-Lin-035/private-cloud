"""Shared path helpers for nested uploads and moves."""
import re
from typing import Optional

MAX_PATH_DEPTH = 16
_INVALID_CHARS = re.compile(r'[\x00-\x1f<>:"\\|?*]')


def sanitize_rel_path(rel_path: str) -> tuple[list[str], Optional[str]]:
    """Split a user-supplied relative path into safe segments.

    Returns (segments, error). Rejects traversal attempts, control chars and
    excessive depth; empty segments are dropped.
    """
    if rel_path is None:
        return [], '缺少路徑'
    raw = rel_path.replace('\\', '/').strip('/')
    if not raw:
        return [], None
    segments = []
    for part in raw.split('/'):
        part = part.strip()
        if not part:
            continue
        if part in ('.', '..'):
            return [], '路徑包含不合法段落'
        if _INVALID_CHARS.search(part) or len(part) > 255:
            return [], f'資料夾名稱不合法: {part[:30]}'
        segments.append(part)
    if len(segments) > MAX_PATH_DEPTH:
        return [], f'路徑深度超過上限 {MAX_PATH_DEPTH}'
    return segments, None


def unique_name(base: str, taken: set[str]) -> str:
    """Return base or 'name (1).ext' style increments absent from taken."""
    if base not in taken:
        return base
    if '.' in base and not base.startswith('.'):
        stem, dot, ext = base.rpartition('.')
    else:
        stem, dot, ext = base, '', ''
    i = 1
    while True:
        candidate = f"{stem} ({i}){dot}{ext}" if dot else f"{stem} ({i})"
        if candidate not in taken:
            return candidate
        i += 1
