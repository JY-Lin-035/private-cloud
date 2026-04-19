from celery import Celery
import smtplib
from email.message import EmailMessage
from app.config import settings
import platform
import logging

# 設定 Logging 方便在 Celery Worker 終端機看到報錯
logger = logging.getLogger(__name__)

# 建立 Celery App
celery_app = Celery(
    'email_tasks',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# 根據作業系統自動調整配置
if platform.system() == 'Windows':
    # Windows 不支援 Fork，必須使用 solo 模式
    worker_pool = 'solo'
else:
    # Linux/Mac 建議使用 prefork 提升效能
    worker_pool = 'prefork'

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    task_always_eager=False,
    worker_pool=worker_pool,
    worker_prefetch_multiplier=1,
)

def _send_email(message: EmailMessage):
    """內部輔助函式：處理 SMTP 寄送邏輯"""
    # 根據 Port 決定使用標準 SMTP 還是 SSL 直接加密 (Port 465)
    if settings.SMTP_PORT == 587:
        smtp_client = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT)
    else:
        smtp_client = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT)

    with smtp_client as smtp:
        # 如果是 Port 587，需要進行 STARTTLS 握手
        if settings.SMTP_PORT == 587:
            smtp.ehlo()    # 跟伺服器打招呼
            smtp.starttls() # 升級加密
            smtp.ehlo()    # 升級後再打一次招呼 (標準做法)
        
        # 登入
        if settings.SMTP_USER and settings.SMTP_PASSWORD:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        
        # 寄信
        smtp.send_message(message)

@celery_app.task(bind=True, max_retries=3)
def send_verification_email_task(self, user_id: int, email: str, hash_value: str, signature: str):
    """發送電子信箱驗證連結"""
    try:
        message = EmailMessage()
        message["From"] = settings.SMTP_FROM
        message["To"] = email
        message["Subject"] = "Meow 請驗證電子信箱地址"
        
        body = f"""
        請點擊以下連結驗證您的電子信箱地址：
        
        {settings.APP_URL}/api/email/verify/{user_id}/{hash_value}?signature={signature}
        
        如果您沒有註冊帳戶，則無需採取進一步操作。
        """
        message.set_content(body)

        _send_email(message)
        return {"status": "success", "to": email}

    except Exception as e:
        logger.error(f"發送驗證信失敗: {str(e)}")
        # 自動重試機制 (例如 60 秒後重試)
        # raise self.retry(exc=e, countdown=60) 
        return {"status": "error", "error": str(e)}

@celery_app.task(bind=True, max_retries=3)
def send_code_email_task(self, email: str, code: str, subject: str):
    """發送數字驗證碼"""
    try:
        message = EmailMessage()
        message["From"] = settings.SMTP_FROM
        message["To"] = email
        message["Subject"] = subject
        
        body = f"""
        您的驗證碼為: {code}
        
        請使用此驗證碼完成您的操作。該驗證碼在短時間內有效。
        """
        message.set_content(body)

        _send_email(message)
        return {"status": "success", "to": email}

    except Exception as e:
        logger.error(f"發送驗證碼失敗: {str(e)}")
        return {"status": "error", "error": str(e)}