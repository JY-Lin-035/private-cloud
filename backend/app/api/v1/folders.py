from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.schemas.folder import (
    CreateFolderRequest, RenameFolderRequest, DeleteFolderRequest, RestoreFolderRequest,
    FolderCreateResponse, FolderRenameResponse, FolderDeleteResponse, FolderRestoreResponse
)
from app.services.folder_service import FolderService
from app.api.dependencies import get_db, get_current_user_id
from app.utils import logger as log

router = APIRouter(prefix="/api/folders", tags=["folders"])
logger = log.get_logger("folders_api.log")


@router.post("/create")
async def create_folder(
    request: CreateFolderRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Create a new folder."""
    try:
        logger.info(f"Create folder request received, user_id: {user_id}, parent_folder_uuid: {request.parent_folder_uuid}, name: {request.name}")
        
        folder_service = FolderService(db)
        
        result = folder_service.create(user_id, request.parent_folder_uuid, request.name)
        logger.info(f"Create folder result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Create folder error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Folder created successfully")
        return result
    except Exception as e:
        logger.error(f"Create folder endpoint error: {e}")
        raise


@router.put("/rename")
async def rename_folder(
    request: RenameFolderRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Rename a folder."""
    try:
        logger.info(f"Rename folder request received, user_id: {user_id}, folder_uuid: {request.folder_uuid}, name: {request.name}")
        
        folder_service = FolderService(db)
        
        result = folder_service.rename(user_id, request.folder_uuid, request.name)
        logger.info(f"Rename folder result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Rename folder error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Folder renamed successfully")
        return result
    except Exception as e:
        logger.error("Rename folder endpoint error", e)
        raise


@router.delete("/delete")
async def delete_folder(
    request: DeleteFolderRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Delete a folder (soft or hard)."""
    try:
        logger.info(f"Delete folder request received, user_id: {user_id}, folder_uuid: {request.folder_uuid}, permanent: {request.permanent}")
        
        folder_service = FolderService(db)
        
        result = folder_service.delete(user_id, request.folder_uuid, request.permanent)
        logger.info(f"Delete folder result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Delete folder error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Folder deleted successfully")
        return result
    except Exception as e:
        logger.error("Delete folder endpoint error", e)
        raise


@router.post("/restore")
async def restore_folder(
    request: RestoreFolderRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Restore a soft-deleted folder."""
    try:
        logger.info(f"Restore folder request received, user_id: {user_id}, folder_uuid: {request.folder_uuid}")
        
        folder_service = FolderService(db)
        
        result = folder_service.restore(user_id, request.folder_uuid)
        logger.info(f"Restore folder result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Restore folder error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Folder restored successfully")
        return result
    except Exception as e:
        logger.error("Restore folder endpoint error", e)
        raise


@router.get("/home")
async def get_home_folder(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get the user's Home folder UUID."""
    try:
        logger.info(f"Get home folder request received, user_id: {user_id}")
        
        folder_service = FolderService(db)
        home_folder = folder_service.folder_repo.get_home_folder(user_id)
        
        if not home_folder:
            logger.error(f"Home folder not found for user_id: {user_id}")
            raise HTTPException(status_code=404, detail="Home folder not found")
        
        logger.info(f"Home folder found: {home_folder.uuid}")
        return {"uuid": home_folder.uuid, "name": home_folder.name}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get home folder endpoint error: {e}")
        raise


@router.get("/path")
async def get_folder_path(
    folder_uuid: str = Query(...),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get the full path from root to the current folder."""
    try:
        logger.info(f"Get folder path request received, user_id: {user_id}, folder_uuid: {folder_uuid}")
        
        folder_service = FolderService(db)
        path = folder_service.folder_repo.get_folder_path(folder_uuid)
        
        logger.info(f"Folder path retrieved: {len(path)} levels")
        return {"path": path}
    except Exception as e:
        logger.error(f"Get folder path endpoint error: {e}")
        raise


@router.get("/list")
async def list_folders(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get all folders by owner."""
    try:
        logger.info(f"List folders request received, user_id: {user_id}")
        
        folder_service = FolderService(db)
        
        result = folder_service.get_by_owner(user_id)
        logger.info(f"List folders result: {result}")
        
        if result and 'error' in result:
            logger.error(f"List folders error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Folders listed successfully")
        return result
    except Exception as e:
        logger.error("List folders endpoint error", e)
        raise


@router.get("/trash")
async def list_trash(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get soft-deleted folders by owner."""
    try:
        logger.info(f"List trash folders request received, user_id: {user_id}")
        
        folder_service = FolderService(db)
        
        result = folder_service.get_trash(user_id)
        logger.info(f"List trash folders result: {result}")
        
        if result and 'error' in result:
            logger.error(f"List trash folders error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Trash folders listed successfully")
        return result
    except Exception as e:
        logger.error("List trash folders endpoint error", e)
        raise
