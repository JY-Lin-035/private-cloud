from typing import Optional
from app.config import settings
from app.utils.security import generate_signed_url, generate_verification_code
from redis import Redis


class EmailService:
    def __init__(self, celery_app, redis_client: Redis = None):
        self.celery = celery_app
        self.redis = redis_client
    
    def send_verification_email(self, user_id: int, email: str):
        """Queue email verification email."""
        from app.tasks.email_tasks import send_verification_email_task
        # Generate signature for the email
        hash_value, signature, timestamp, secret_key = generate_signed_url(user_id, email)
        # Store in Redis: user_id|hash|timestamp|secret_key with expiration
        if self.redis:
            self.redis.setex(
                f"registerVerifyMail:{user_id}",
                settings.MAIL_VAL_EXPIRE_TIME * 60,
                f"{user_id}|{hash_value}|{timestamp}|{secret_key}"
            )
        send_verification_email_task.delay(user_id, email, hash_value, signature)
    
    def send_code_email(self, email: str, code: str, subject: str):
        """Queue verification code email."""
        from app.tasks.email_tasks import send_code_email_task
        send_code_email_task.delay(email, code, subject)
