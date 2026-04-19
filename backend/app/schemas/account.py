from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=5, max_length=100, pattern=r'^[A-Za-z0-9]+$')
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=100)
    
    @field_validator('password')
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError('密碼必須包含至少一個大寫字母')
        if not any(c.islower() for c in v):
            raise ValueError('密碼必須包含至少一個小寫字母')
        if not any(c.isdigit() for c in v):
            raise ValueError('密碼必須包含至少一個數字')
        unique_symbols = set(c for c in v if not c.isalnum())
        if len(unique_symbols) < 3:
            raise ValueError('密碼必須包含至少三種不同的符號')
        return v


class LoginRequest(BaseModel):
    username: str
    password: str


class ModifyEmailRequest(BaseModel):
    email: EmailStr
    check_email: EmailStr
    code: str


class ModifyPasswordRequest(BaseModel):
    now_pw: str = Field(..., alias="nowPW")
    new_pw: str = Field(..., min_length=12, max_length=100, alias="newPW")
    
    class Config:
        populate_by_name = True
    
    @field_validator('new_pw')
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError('密碼必須包含至少一個大寫字母')
        if not any(c.islower() for c in v):
            raise ValueError('密碼必須包含至少一個小寫字母')
        if not any(c.isdigit() for c in v):
            raise ValueError('密碼必須包含至少一個數字')
        unique_symbols = set(c for c in v if not c.isalnum())
        if len(unique_symbols) < 3:
            raise ValueError('密碼必須包含至少三種不同的符號')
        return v


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    password: str = Field(..., min_length=12, max_length=100)
    
    @field_validator('password')
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError('密碼必須包含至少一個大寫字母')
        if not any(c.islower() for c in v):
            raise ValueError('密碼必須包含至少一個小寫字母')
        if not any(c.isdigit() for c in v):
            raise ValueError('密碼必須包含至少一個數字')
        unique_symbols = set(c for c in v if not c.isalnum())
        if len(unique_symbols) < 3:
            raise ValueError('密碼必須包含至少三種不同的符號')
        return v


class GetCodeRequest(BaseModel):
    email: EmailStr
    mode: str  # 'pw' for password reset, 'mail' for email change


class AccountResponse(BaseModel):
    id: int
    name: str
    email: str
    signal_file_size: int
    total_file_size: int
    used_size: int
    identity: int
    enable: bool
    email_verified_at: Optional[datetime]
    last_sign_in_date: Optional[datetime]
    
    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    message: str
    email: str


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error: str
