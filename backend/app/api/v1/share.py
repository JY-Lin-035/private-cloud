from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.schemas.share import ShareLinkRequest, ShareListResponse, ShareLinkResponse, ShareDeleteResponse
from app.services.share_service import ShareService
from app.api.dependencies import get_db, get_current_user_id
from app.utils import logger as log

router = APIRouter(prefix="/api/share", tags=["share"])
logger = log.get_logger("share_api.log")


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
    """Create a share link for a file."""
    try:
        logger.info(f"Create share link request received, user_id: {user_id}, dir: {request.dir}, filename: {request.filename}")
        
        share_service = ShareService(db)
        
        result = share_service.create_link(user_id, request.dir, request.filename)
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
    dir: str = Query(None),
    filename: str = Query(None),
    link: str = Query(None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Delete a share link."""
    try:
        logger.info(f"Delete share link request received, user_id: {user_id}, dir: {dir}, filename: {filename}, link: {link}")
        
        share_service = ShareService(db)
        
        result = share_service.delete_link(user_id, dir, filename, link)
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
    db: Session = Depends(get_db)
):
    """Download a file via share link (no authentication required)."""
    global logger
    logger.info(f"Download shared file request received, link: {link}")
    try:        
        share_service = ShareService(db)
        
        result = share_service.download(link)
        logger.info(f"Download shared file result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Download shared file error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Shared file downloaded successfully")
        return FileResponse(path=result['real_path'], filename=result['filename'])
    except Exception as e:
        logger.error(f"Download shared file endpoint error: {e}")
        raise
