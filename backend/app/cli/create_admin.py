"""Create an initial admin account directly in the DB.

Usage:
    uv run python -m app.cli.create_admin --username admin --email a@b.c [--password '...' | --generate]
"""
import argparse
import re
import secrets
import string
import sys
import uuid as uuid_mod
from datetime import datetime

from app.constants import Identity, StorageLimits
from app.models.account import Account
from app.models.folder import Folder
from app.utils.security import hash_password
from app.database import SessionLocal


def generate_password() -> str:
    """Random password satisfying the site policy: upper/lower/digit/3+ distinct symbols, 12-100."""
    uppers = "".join(secrets.choice(string.ascii_uppercase) for _ in range(3))
    lowers = "".join(secrets.choice(string.ascii_lowercase) for _ in range(5))
    digits = "".join(secrets.choice(string.digits) for _ in range(3))
    symbols = "".join(secrets.choice("!@#$%^&*()-_=+[]{};:,") for _ in range(4))
    alphabet = uppers + lowers + digits + symbols
    extra = "".join(secrets.choice(alphabet) for _ in range(4))
    chars = list(alphabet + extra)
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)


def validate(username: str, email: str, password: str) -> list[str]:
    errors = []
    if not re.match(r'^[A-Za-z0-9]{5,100}$', username):
        errors.append('username must be 5-100 alphanumeric chars')
    if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
        errors.append('invalid email')
    if len(password) < 12 or not re.search(r'[A-Z]', password) or not re.search(r'[a-z]', password) \
            or not re.search(r'\d', password) or len(set(re.findall(r'[^A-Za-z0-9]', password))) < 3:
        errors.append('password must be >=12 chars with upper/lower/digit and 3+ distinct symbols')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description='Create an admin account')
    parser.add_argument('--username', required=True)
    parser.add_argument('--email', required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--password')
    group.add_argument('--generate', action='store_true', help='generate and print a policy-compliant password')
    args = parser.parse_args()

    password = generate_password() if args.generate else args.password
    errors = validate(args.username, args.email, password)
    if errors:
        for e in errors:
            print(f'ERROR: {e}', file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        exists = db.query(Account).filter(
            (Account.name == args.username) | (Account.email == args.email)
        ).first()
        if exists:
            print('ERROR: username or email already exists', file=sys.stderr)
            return 2
        account = Account(
            name=args.username,
            email=args.email,
            password=hash_password(password),
            identity=Identity.ADMIN,
            enable=True,
            email_verified_at=datetime.utcnow(),
            used_size=0,
            total_file_size=StorageLimits.DEFAULT_TOTAL_FILE_SIZE,
        )
        db.add(account)
        db.flush()
        db.add(Folder(uuid=str(uuid_mod.uuid4()), owner_id=account.id, parent_id=None, name='Home', size=0, is_system=True))
        db.commit()
        print(f'admin created: {args.username}')
        if args.generate:
            print(f'password: {password}')
        return 0
    finally:
        db.close()


if __name__ == '__main__':
    sys.exit(main())
