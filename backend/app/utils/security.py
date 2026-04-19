import secrets
import hashlib
import hmac
import time
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer
from app.config import settings

# Use Argon2id to match Laravel's default hashing driver
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__time_cost=6,          # Laravel ARGON_TIME
    argon2__memory_cost=65536,    # Laravel ARGON_MEMORY
    argon2__parallelism=6,        # Laravel ARGON_THREADS
    argon2__hash_len=32,
    argon2__salt_len=16
)
serializer = URLSafeTimedSerializer(settings.APP_URL)


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def generate_session_token(user_id: int) -> str:
    """Generate a session token in format: id|token (matching Laravel Sanctum format)."""
    token = secrets.token_urlsafe(32)
    return f"{user_id}|{token}"


def verify_session_token_format(token: str) -> bool:
    """Verify if token has correct format (id|token)."""
    if '|' not in token:
        return False
    parts = token.split('|')
    if len(parts) != 2:
        return False
    try:
        int(parts[0])
        return True
    except ValueError:
        return False


def hash_token(token: str) -> str:
    """Hash a token for storage (matching Laravel's token hashing)."""
    return hashlib.sha256(token.encode()).hexdigest()


def generate_signed_url(user_id: int, email: str) -> str:
    """Generate a signed URL for email verification (Laravel style)."""
    # Generate random 16-character secret key
    secret_key = secrets.token_urlsafe(16)
    
    # Current timestamp
    timestamp = int(time.time())
    
    # Create hash: SHA256(email + timestamp + secret_key)
    hash_value = hashlib.sha256(f"{email}{timestamp}{secret_key}".encode()).hexdigest()
    
    # Create signature: HMAC-SHA256(user_id + hash + timestamp, secret_key)
    signature_data = f"{user_id}{hash_value}{timestamp}"
    signature = hmac.new(secret_key.encode(), signature_data.encode(), hashlib.sha256).hexdigest()
    
    # Return the hash (to be stored in Redis) and the signature
    # The signature will be used in the URL
    return hash_value, signature, timestamp, secret_key


def verify_signed_url(user_id: int, hash_value: str, signature: str, redis_client) -> bool:
    """Verify a signed URL by checking Redis."""
    try:
        # Get stored data from Redis
        stored_data = redis_client.get(f"registerVerifyMail:{user_id}")
        if not stored_data:
            return False
        
        # Check if data is bytes or string
        if isinstance(stored_data, bytes):
            stored_data = stored_data.decode()
        
        # Parse stored data: user_id|hash|timestamp|secret_key
        parts = stored_data.split('|')
        if len(parts) != 4:
            return False
        
        stored_user_id, stored_hash, stored_timestamp, stored_secret_key = parts
        
        # Check if user_id matches
        if str(user_id) != stored_user_id:
            return False
        
        # Check if hash matches
        if hash_value != stored_hash:
            return False
        
        # Check if expired (timestamp in seconds, MAIL_VAL_EXPIRE_TIME in minutes)
        current_time = int(time.time())
        stored_time = int(stored_timestamp)
        max_age = settings.MAIL_VAL_EXPIRE_TIME * 60  # Convert minutes to seconds
        if current_time - stored_time > max_age:
            return False
        
        # Verify signature
        signature_data = f"{user_id}{hash_value}{stored_timestamp}"
        expected_signature = hmac.new(stored_secret_key.encode(), signature_data.encode(), hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(signature, expected_signature):
            return False
        
        return True
    except Exception as e:
        return False


def generate_verification_code(length: int = 8) -> str:
    """Generate a random verification code."""
    return secrets.token_urlsafe(length)[:length]
