from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.services.share_service import ShareService
from app.services import zip_service
from app.api.dependencies import get_db, get_current_user_id
from app.api.rate_limit import rate_limit
from app.utils import logger as log

router = APIRouter(prefix="/api/share", tags=["share"])
logger = log.get_logger("share_api.log")


class ShareLinkRequest(BaseModel):
    item_uuid: str
    item_type: str  # 'folder' or 'file'
    limited_date: Optional[str] = None  # Expiration date for the share link (ISO string)
    password: Optional[str] = None  # None = keep, "" = clear, text = set


class ShareStatusRequest(BaseModel):
    link: str


class ShareVerifyRequest(BaseModel):
    link: str
    password: str


@router.get("/getList")
async def get_share_list(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get all share links for a user."""
    try:
        logger.info(f"Get share list request received, user_id: {user_id}")
        
        share_service = ShareService(db)
        
        result = share_service.get_list(user_id)
        logger.info(f"Get share list result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Get share list error {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        # Match Laravel format: return 'share' key instead of 'list'
        return {'share': result['list']}
    except Exception as e:
        logger.error(f"Get share list endpoint error {e}")
        raise


@router.post("/getLink")
async def create_share_link(
    request: ShareLinkRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Create a share link for a folder or file."""
    try:
        logger.info(f"Create share link request received, user_id: {user_id}, item_uuid: {request.item_uuid}, item_type: {request.item_type}, limited_date_raw: {request.limited_date}")
        
        # Parse limited_date string to datetime
        parsed_limited_date = None
        if request.limited_date:
            try:
                # Handle format: "2026-07-17T17:00:00" (local time, no timezone)
                # Also handle ISO format: "2026-07-17T09:00:00.000Z"
                cleaned = request.limited_date.replace('Z', '+00:00')
                parsed_limited_date = datetime.fromisoformat(cleaned)
                logger.info(f"Parsed limited_date: {parsed_limited_date}")
            except Exception as e:
                logger.error(f"Failed to parse limited_date '{request.limited_date}': {e}")
        
        share_service = ShareService(db)
        
        result = share_service.create_link(user_id, request.item_uuid, request.item_type, limited_date=parsed_limited_date, password=request.password)
        logger.info(f"Create share link result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Create share link error {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Share link created successfully")
        # Match Laravel format: return plain URL string
        return result['url']
    except Exception as e:
        logger.error(f"Create share link endpoint error {e}")
        raise


@router.delete("/deleteLink")
async def delete_share_link(
    item_uuid: str = Query(...),
    item_type: str = Query(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Delete a share link."""
    try:
        logger.info(f"Delete share link request received, user_id: {user_id}, item_uuid: {item_uuid}, item_type: {item_type}")
        
        share_service = ShareService(db)
        
        result = share_service.delete_link(user_id, item_uuid, item_type)
        logger.info(f"Delete share link result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Delete share link error {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Share link deleted successfully")
        return result
    except Exception as e:
        logger.error(f"Delete share link endpoint error {e}")
        raise


@router.get("/downloadFile")
async def download_shared_file(
    link: str = Query(...),
    ticket: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Download a file via share link (no authentication required)."""
    global logger
    logger.info(f"Download shared file request received, link: {link}")
    try:        
        share_service = ShareService(db)
        
        result = share_service.download(link, ticket=ticket)
        logger.info(f"Download shared file result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Download shared file error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Shared file downloaded successfully")
        return FileResponse(
            path=result['real_path'], 
            filename=result['filename'],
            media_type=result.get('mime_type', 'application/octet-stream')
        )
    except Exception as e:
        logger.error(f"Download shared file endpoint error: {e}")
        raise


@router.post("/status")
async def share_status(
    request: ShareStatusRequest,
    db: Session = Depends(get_db)
):
    """Public: report whether a link exists / needs password / is expired. No content leaked."""
    share_service = ShareService(db)
    result = share_service.get_share_status(request.link)
    if result and 'error' in result:
        raise HTTPException(status_code=result['stateCode'], detail=result['error'])
    return {
        'exists': result['exists'],
        'type': result['type'],
        'password_required': result['password_required'],
        'expired': result['expired'],
    }


@router.post("/verifyPassword", dependencies=[Depends(rate_limit(5, 300))])
async def share_verify_password(
    request: ShareVerifyRequest,
    db: Session = Depends(get_db)
):
    """Public: exchange the share password for a short-lived download ticket."""
    share_service = ShareService(db)
    result = share_service.verify_share_password(request.link, request.password)
    if result and 'error' in result:
        raise HTTPException(status_code=result['stateCode'], detail=result['error'])
    logger.info(f"Share password verified, ticket issued for link: {request.link}")
    return {'ticket': result['ticket'], 'expires_in': result['expires_in']}


class ShareItemsRequest(BaseModel):
    link: str
    paths: list[str]
    ticket: Optional[str] = None


@router.get("/browse")
async def share_browse(
    link: str = Query(...),
    sub: str = Query(''),
    ticket: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Public: browse one level inside a shared folder."""
    result = ShareService(db).browse(link, sub, ticket)
    if result and 'error' in result:
        raise HTTPException(status_code=result['stateCode'], detail=result['error'])
    return {k: v for k, v in result.items() if k != 'stateCode'}


@router.get("/downloadFolder")
async def share_download_folder(
    link: str = Query(...),
    ticket: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Public: download the whole shared folder as a zip."""
    share_service = ShareService(db)
    folder, err = share_service._resolve_shared_folder(link, ticket)
    if err:
        raise HTTPException(status_code=err['stateCode'], detail=err['error'])
    items, kept_files, _ = zip_service.collect_zip_items(db, folder.owner_id, [], [folder.uuid])
    logger.info(f"Public folder zip: link={link}, files={kept_files}")
    return zip_service.build_zip_response(items, folder.name)


@router.post("/downloadItems", dependencies=[Depends(rate_limit(10, 60))])
async def share_download_items(
    request: ShareItemsRequest,
    db: Session = Depends(get_db)
):
    """Public: download selected paths inside a shared folder as one zip."""
    share_service = ShareService(db)
    owner_id, file_uuids, folder_uuids, err = share_service.collect_shared_items(request.link, request.paths, request.ticket)
    if err:
        raise HTTPException(status_code=err['stateCode'], detail=err['error'])
    items, kept_files, kept_folders = zip_service.collect_zip_items(db, owner_id, file_uuids, folder_uuids)
    logger.info(f"Public items zip: link={request.link}, files={kept_files}, folders={kept_folders}")
    return zip_service.build_zip_response(items, 'shared-download')
