from typing import Tuple


def format_email(email: str) -> str:
    """Format email address - lowercase and remove dots from Gmail addresses."""
    email = email.lower()
    username, domain = email.split('@', 1)
    
    if domain == 'gmail.com':
        username = username.replace('.', '')
    
    return f"{username}@{domain}"


def mask_email(email: str) -> str:
    """Mask email address for display - similar to Laravel's lock() function."""
    username, domain = email.split('@', 1)
    length = len(username)
    
    if length <= 2:
        masked_username = '*' * 5
    else:
        masked_username = f"{username[0]}*****{username[-1]}"
    
    return f"{masked_username}@{domain}"
