"""Signed, expiring tickets for password-protected share links."""
from secrets import token_hex

from itsdangerous import BadSignature, SignatureExpired, TimestampSigner

from app.config import settings

_EPHEMERAL_SECRET = token_hex(32)


def _signer() -> TimestampSigner:
    secret = settings.SHARE_TICKET_SECRET or _EPHEMERAL_SECRET
    return TimestampSigner(secret_key=secret, salt="meow-share-ticket")


def issue_ticket(share_hash: str) -> str:
    return _signer().sign(share_hash).decode()


def verify_ticket(share_hash: str, ticket: str | None) -> bool:
    if not ticket:
        return False
    try:
        signed = _signer().unsign(ticket, max_age=settings.SHARE_TICKET_TTL_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    if isinstance(signed, bytes):
        signed = signed.decode()
    return signed == share_hash
