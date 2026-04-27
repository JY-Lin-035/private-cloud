from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from redis import Redis
from app.schemas.file import (
    FileUploadRequest, DeleteFileRequest, RestoreFileRequest,
    FileListResponse, StorageInfoResponse, FileUploadResponse, FileDeleteResponse, FileRestoreResponse
)
from app.services.file_service import FileService
from app.api.dependencies import get_db, get_redis, get_current_user_id
from app.utils import logger as log

router = APIRouter(prefix="/api/files", tags=["files"])
logger = log.get_logger("files_api.log")


@router.get("/storage")
async def get_storage(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get storage usage information."""
    try:
        logger.info(f"Get storage request received, user_id: {user_id}")
        
        file_service = FileService(db)
        
        result = file_service.get_storage(user_id)
        logger.info(f"Get storage result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Get storage error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        return result
    except Exception as e:
        logger.error(f"Get storage endpoint error: {e}")
        raise


@router.get("/list")
async def get_file_list(
    parent_folder_uuid: str = Query(None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get list of files in a folder."""
    try:
        logger.info(f"Get file list request received, user_id: {user_id}, parent_folder_uuid: {parent_folder_uuid}")
        
        file_service = FileService(db)
        
        result = file_service.get_file_list(user_id, parent_folder_uuid)
        logger.info(f"Get file list result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Get file list error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        return result
    except Exception as e:
        logger.error(f"Get file list endpoint error: {e}")
        raise


@router.post("/uploadFile")
async def upload_file(
    file: UploadFile = File(...),
    parent_folder_uuid: str = Form(None),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Upload a file."""
    try:
        logger.info(f"Upload file request received, user_id: {user_id}, parent_folder_uuid: {parent_folder_uuid}, filename: {file.filename}")
        
        file_service = FileService(db)
        
        # Read file content
        file_content = await file.read()
        file_size = len(file_content)
        
        # Create a mock file object with file attribute
        class MockFile:
            def __init__(self, filename, content):
                self.filename = filename
                self.file = type('obj', (object,), {'read': lambda *args, **kwargs: content})()
        
        mock_file = MockFile(file.filename, file_content)
        
        result = file_service.upload_file(user_id, parent_folder_uuid, mock_file, file_size)
        logger.info(f"Upload file result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Upload file error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("File uploaded successfully")
        return result
    except Exception as e:
        logger.error(f"Upload file endpoint error: {e}")
        raise


@router.get("/download")
async def download_file(
    file_uuid: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Download a file."""
    try:
        logger.info(f"Download file request received, user_id: {user_id}, file_uuid: {file_uuid}")

        file_service = FileService(db)

        result = file_service.download(user_id, file_uuid)
        logger.info(f"Download file result: {result}")

        if result and 'error' in result:
            logger.error(f"Download file error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        logger.info("File downloaded successfully")
        return FileResponse(
            path=result['real_path'],
            filename=result['filename'],
            media_type=result['mime_type'],
            headers={'Content-Disposition': f'attachment; filename="{result["filename"]}"'}
        )
    except Exception as e:
        logger.error(f"Download file endpoint error: {e}")
        raise


@router.delete("/delete")
async def delete_file(
    request: DeleteFileRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Delete a file (soft or hard)."""
    try:
        logger.info(f"Delete file request received, user_id: {user_id}, file_uuid: {request.file_uuid}, permanent: {request.permanent}")
        
        file_service = FileService(db)
        
        result = file_service.delete(user_id, request.file_uuid, request.permanent)
        logger.info(f"Delete file result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Delete file error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("File deleted successfully")
        return result
    except Exception as e:
        logger.error(f"Delete file endpoint error: {e}")
        raise


@router.post("/restore")
async def restore_file(
    request: RestoreFileRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Restore a soft-deleted file."""
    try:
        logger.info(f"Restore file request received, user_id: {user_id}, file_uuid: {request.file_uuid}")
        
        file_service = FileService(db)
        
        result = file_service.restore(user_id, request.file_uuid)
        logger.info(f"Restore file result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Restore file error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("File restored successfully")
        return result
    except Exception as e:
        logger.error(f"Restore file endpoint error: {e}")
        raise


@router.get("/trash")
async def list_trash(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get soft-deleted files by owner."""
    try:
        logger.info(f"List trash files request received, user_id: {user_id}")
        
        file_service = FileService(db)
        
        result = file_service.get_trash(user_id)
        logger.info(f"List trash files result: {result}")
        
        if result and 'error' in result:
            logger.error(f"List trash files error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Trash files listed successfully")
        return result
    except Exception as e:
        logger.error(f"List trash files endpoint error: {e}")
        raise
