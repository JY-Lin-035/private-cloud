import secrets
from typing import Optional
from redis import Redis
from app.services import batch_ops
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.schemas.folder import (
    CreateFolderRequest, RenameFolderRequest, DeleteFolderRequest, RestoreFolderRequest,
    FolderCreateResponse, FolderRenameResponse, FolderDeleteResponse, FolderRestoreResponse
)
from app.services.folder_service import FolderService
from app.services import zip_service
from app.api.dependencies import get_db, get_current_user_id, get_current_user_id_optional, get_redis
from app.config import settings
from app.utils import logger as log

router = APIRouter(prefix="/api/folders", tags=["folders"])
logger = log.get_logger("folders_api.log")


@router.post("/create")
async def create_folder(
    request: CreateFolderRequest,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    batch_ops.assert_not_deleting(redis, request.parent_folder_uuid)
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
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Rename a folder."""
    batch_ops.assert_not_deleting(redis, request.folder_uuid)
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
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Delete a folder (soft or hard)."""
    batch_ops.assert_not_deleting(redis, request.folder_uuid)
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
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Restore a soft-deleted folder."""
    batch_ops.assert_not_deleting(redis, request.folder_uuid)
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
        folder = folder_service.folder_repo.get_by_uuid(folder_uuid)
        if not folder or folder.owner_id != user_id or folder.deleted_at is not None:
            raise HTTPException(status_code=404, detail="找不到資料夾")
        path = folder_service.folder_repo.get_folder_path(folder_uuid)
        
        logger.info(f"Folder path retrieved: {len(path)} levels")
        return {"path": path}
    except HTTPException:
        raise
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


class FolderMoveRequest(BaseModel):
    folder_uuids: list[str] = Field(max_length=2000)
    target_folder_uuid: str | None = None
    target_path: str | None = None


@router.post("/move")
async def move_folders(
    request: FolderMoveRequest,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Move folders to an existing folder or a (auto-created) nested path."""
    batch_ops.assert_not_deleting(redis, *request.folder_uuids, request.target_folder_uuid)
    target = request.target_folder_uuid
    if not target and request.target_path:
        resolved = FolderService(db).resolve_or_create_path(user_id, None, request.target_path)
        if 'error' in resolved:
            raise HTTPException(status_code=resolved['stateCode'], detail=resolved['error'])
        target = resolved['uuid']
    if not target:
        raise HTTPException(status_code=400, detail='需要提供目標資料夾或路徑')

    result = FolderService(db).move_folders(user_id, request.folder_uuids, target)
    if result and 'error' in result:
        raise HTTPException(status_code=result['stateCode'], detail=result['error'])
    logger.info(f"Moved {len(result['moved'])} folders for user {user_id} -> {target}; renamed={result['renamed']}")
    return result


@router.get("/downloadToken")
async def get_folder_download_token(
    folder_uuid: str,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Short-lived one-time token enabling a native (streaming) folder zip download."""
    batch_ops.assert_not_deleting(redis, folder_uuid)
    svc = FolderService(db)
    folder = svc.folder_repo.get_by_uuid(folder_uuid)
    if not folder or folder.owner_id != user_id or folder.deleted_at:
        raise HTTPException(status_code=404, detail='找不到資料夾')
    token = secrets.token_hex(32)
    expire = settings.DOWNLOAD_TOKEN_EXPIRE_SECONDS
    redis.setex(f"download_folder_token:{token}", expire, f"{user_id}:{folder_uuid}")
    return JSONResponse({"token": token, "folder_uuid": folder_uuid, "expires_in": expire})


@router.get("/download")
async def download_folder(
    folder_uuid: str = Query(...),
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: Optional[int] = Depends(get_current_user_id_optional)
):
    """Stream a whole folder as one zip archive (session or one-time token)."""
    svc = FolderService(db)
    if token:
        redis_key = f"download_folder_token:{token}"
        try:
            tdata = redis.getdel(redis_key)
        except Exception:
            tdata = redis.get(redis_key)
            if tdata:
                redis.delete(redis_key)
        if not tdata:
            raise HTTPException(status_code=401, detail="Invalid or expired download token")
        tdata_str = tdata.decode() if isinstance(tdata, bytes) else tdata
        parts = tdata_str.split(":")
        if len(parts) != 2:
            raise HTTPException(status_code=400, detail="Invalid token data")
        try:
            user_id = int(parts[0])
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid or expired download token")
        if parts[1] != folder_uuid:
            raise HTTPException(status_code=403, detail="Token does not match folder")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    folder = svc.folder_repo.get_by_uuid(folder_uuid)
    if not folder or folder.owner_id != user_id or folder.deleted_at:
        raise HTTPException(status_code=404, detail='找不到資料夾')

    items, kept_files, _ = zip_service.collect_zip_items(db, user_id, [], [folder_uuid])
    logger.info(f"Folder zip download for user {user_id}: {folder_uuid}, {len(items)} zip entries")
    return zip_service.build_zip_response(items, folder.name)
