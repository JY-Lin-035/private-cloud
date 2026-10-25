from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.api.dependencies import get_db, require_admin
from app.schemas.feature_flag import FeatureFlagUpdate
from app.services.feature_flag_service import (
    ALLOWED_FEATURE_KEYS,
    FeatureFlagService,
)
from app.utils import logger as log

router = APIRouter(prefix="/api/accounts", tags=["settings"])
logger = log.get_logger("settings_api.log")


@router.get("/settings/public")
async def public_settings(db: Session = Depends(get_db)):
    """Minimal feature state needed by the public login/register pages."""
    return FeatureFlagService(db).public_flags()


@router.get("/admin/settings/features")
async def list_feature_flags(request: Request, db: Session = Depends(get_db)):
    """List all feature flags (admin only)."""
    require_admin(request)
    svc = FeatureFlagService(db)
    return [
        {
            "key": flag.key,
            "enabled": bool(flag.enabled),
            "effective": svc.effective_enabled(flag.key),
            "description": flag.description,
        }
        for flag in svc.list_flags()
    ]


@router.put("/admin/settings/features/{key}")
async def update_feature_flag(
    key: str,
    payload: FeatureFlagUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """Toggle a feature flag (admin only, whitelisted keys)."""
    admin = require_admin(request)
    if key not in ALLOWED_FEATURE_KEYS:
        raise HTTPException(status_code=400, detail="Unknown feature key")
    flag = FeatureFlagService(db).set_enabled(key, payload.enabled)
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    logger.info(
        f"FeatureFlag changed: admin_user_id={admin.get('id')} "
        f"key={key} enabled={payload.enabled}"
    )
    from app.utils.security_log import write_event
    write_event("feature_change", None, admin.get("username"), key, f"enabled={payload.enabled}")
    return {"key": flag.key, "enabled": bool(flag.enabled)}
