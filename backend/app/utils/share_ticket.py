"""Signed, expiring tickets for password-protected share links."""
from secrets import token_hex

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from app.config import settings

_EPHEMERAL_SECRET = token_hex(32)


def _signer() -> TimestampSigner:
    secret = settings.SHARE_TICKET_SECRET or _EPHEMERAL_SECRET
    return TimestampSigner(secret_key=secret, salt="meow-share-ticket")


def _payload(share_hash: str, pwd_marker: str) -> str:
    return f"{share_hash}|{pwd_marker}"


def issue_ticket(share_hash: str, pwd_marker: str = "") -> str:
    """pwd_marker ties the ticket to the CURRENT share password hash prefix,
    so rotating/removing the password instantly invalidates issued tickets
    (red-team F9: revocation-by-password-change must actually revoke)."""
    return _signer().sign(_payload(share_hash, pwd_marker)).decode()


def verify_ticket(share_hash: str, ticket: str | None, pwd_marker: str = "") -> bool:
    if not ticket:
        return False
    try:
        signed = _signer().unsign(ticket, max_age=settings.SHARE_TICKET_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    if isinstance(signed, bytes):
        signed = signed.decode()
    return signed == _payload(share_hash, pwd_marker)
