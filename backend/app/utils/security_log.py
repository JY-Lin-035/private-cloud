"""Dedicated security event log: backend/logs/security.log (0600, rotating).

Format (pipe-separated, full data server-side only):
    timestamp | event | ip | actor | target | detail
"""
import logging
import os
from logging.handlers import RotatingFileHandler

_logger = None


def get_security_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, 'security.log')
    logger = logging.getLogger('security')
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(path, maxBytes=10 * 1024 * 1024, backupCount=10, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
        logger.addHandler(handler)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    _logger = logger
    return _logger


def _clean(v) -> str:
    """Neutralise attacker-controlled separators/CR-LF before logging.

    The log is pipe-delimited audit data; a username/detail containing
    newlines or '|' could forge or shift audit rows.
    """
    s = "-" if v is None else str(v)
    return s.replace("\r", " ").replace("\n", " ").replace("|", "/")[:300]


def write_event(kind: str, ip: str, actor: str, target: str, detail: str) -> None:
    get_security_logger().info(" | ".join([_clean(kind), _clean(ip), _clean(actor), _clean(target), _clean(detail)]))
