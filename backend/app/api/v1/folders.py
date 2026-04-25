from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.schemas.folder import CreateFolderRequest, RenameFolderRequest, FolderCreateResponse, FolderRenameResponse, FolderDeleteResponse
from app.services.folder_service import FolderService
from app.api.dependencies import get_db, get_current_user_id
from app.utils.logger_sample import log_info, log_error

router = APIRouter(prefix="/api/folders", tags=["folders"])


@router.post("/createFolder")
async def create_folder(
    request: CreateFolderRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Create a new folder."""
    try:
        log_info("Create folder request received", {"user_id": user_id, "dir": request.dir, "folderName": request.folderName})
        
        folder_service = FolderService(db)
        
        result = folder_service.create(user_id, request.dir, request.folderName)
        log_info("Create folder result", {"result": result})
        
        if result and 'error' in result:
            log_info("Create folder error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("Folder created successfully")
        return result
    except Exception as e:
        log_error("Create folder endpoint error", e)
        raise


@router.put("/renameFolder")
async def rename_folder(
    request: RenameFolderRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Rename a folder."""
    try:
        log_info("Rename folder request received", {"user_id": user_id, "dir": request.dir, "originName": request.originName, "folderName": request.folderName})
        
        folder_service = FolderService(db)
        
        result = folder_service.rename(user_id, request.dir, request.originName, request.folderName)
        log_info("Rename folder result", {"result": result})
        
        if result and 'error' in result:
            log_info("Rename folder error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("Folder renamed successfully")
        return result
    except Exception as e:
        log_error("Rename folder endpoint error", e)
        raise


@router.delete("/deleteFolder")
async def delete_folder(
    dir: str,
    folderName: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Delete a folder."""
    try:
        log_info("Delete folder request received", {"user_id": user_id, "dir": dir, "folderName": folderName})
        
        folder_service = FolderService(db)
        
        result = folder_service.delete(user_id, dir, folderName)
        log_info("Delete folder result", {"result": result})
        
        if result and 'error' in result:
            log_info("Delete folder error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("Folder deleted successfully")
        return result
    except Exception as e:
        log_error("Delete folder endpoint error", e)
        raise
