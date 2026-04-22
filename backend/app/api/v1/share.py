from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.schemas.share import ShareLinkRequest, ShareListResponse, ShareLinkResponse, ShareDeleteResponse
from app.services.share_service import ShareService
from app.api.dependencies import get_db, get_current_user_id
from app.utils.logger_sample import log_info, log_error

router = APIRouter(prefix="/api/share", tags=["share"])


@router.get("/getList")
async def get_share_list(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get all share links for a user."""
    try:
        log_info("Get share list request received", {"user_id": user_id})
        
        share_service = ShareService(db)
        
        result = share_service.get_list(user_id)
        log_info("Get share list result", {"result": result})
        
        if result and 'error' in result:
            log_info("Get share list error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        # Match Laravel format: return 'share' key instead of 'list'
        return {'share': result['list']}
    except Exception as e:
        log_error("Get share list endpoint error", e)
        raise


@router.post("/getLink")
async def create_share_link(
    request: ShareLinkRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Create a share link for a file."""
    try:
        log_info("Create share link request received", {"user_id": user_id, "dir": request.dir, "filename": request.filename})
        
        share_service = ShareService(db)
        
        result = share_service.create_link(user_id, request.dir, request.filename)
        log_info("Create share link result", {"result": result})
        
        if result and 'error' in result:
            log_info("Create share link error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("Share link created successfully")
        # Match Laravel format: return plain URL string
        return result['url']
    except Exception as e:
        log_error("Create share link endpoint error", e)
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
        log_info("Delete share link request received", {"user_id": user_id, "dir": dir, "filename": filename, "link": link})
        
        share_service = ShareService(db)
        
        result = share_service.delete_link(user_id, dir, filename, link)
        log_info("Delete share link result", {"result": result})
        
        if result and 'error' in result:
            log_info("Delete share link error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("Share link deleted successfully")
        return result
    except Exception as e:
        log_error("Delete share link endpoint error", e)
        raise


@router.get("/downloadFile")
async def download_shared_file(
    link: str = Query(...),
    db: Session = Depends(get_db)
):
    """Download a file via share link (no authentication required)."""
    try:
        log_info("Download shared file request received", {"link": link})
        
        share_service = ShareService(db)
        
        result = share_service.download(link)
        log_info("Download shared file result", {"result": result})
        
        if result and 'error' in result:
            log_info("Download shared file error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("Shared file downloaded successfully")
        return FileResponse(path=result['real_path'], filename=result['filename'])
    except Exception as e:
        log_error("Download shared file endpoint error", e)
        raise
