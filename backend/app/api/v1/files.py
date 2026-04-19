from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from redis import Redis
from app.schemas.file import FileUploadRequest, FileListResponse, StorageInfoResponse, FileUploadResponse, FileDeleteResponse
from app.services.file_service import FileService
from app.api.dependencies import get_db, get_redis, get_current_user_id
from app.utils.logger import log_info, log_error

router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/getStorage")
async def get_storage(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get storage usage information."""
    try:
        log_info("Get storage request received", {"user_id": user_id})
        
        file_service = FileService(db)
        
        result = file_service.get_storage(user_id)
        log_info("Get storage result", {"result": result})
        
        if result and 'error' in result:
            log_info("Get storage error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        return result
    except Exception as e:
        log_error("Get storage endpoint error", e)
        raise


@router.get("/getFileList")
async def get_file_list(
    path: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Get list of files in a folder."""
    try:
        log_info("Get file list request received", {"user_id": user_id, "path": path})
        
        file_service = FileService(db)
        
        result = file_service.get_file_list(user_id, path)
        log_info("Get file list result", {"result": result})
        
        if result and 'error' in result:
            log_info("Get file list error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        return result
    except Exception as e:
        log_error("Get file list endpoint error", e)
        raise


@router.post("/uploadFile")
async def upload_file(
    file: UploadFile = File(...),
    dir: str = Form(""),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Upload a file."""
    try:
        log_info("Upload file request received", {"user_id": user_id, "dir": dir, "filename": file.filename})
        
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
        
        result = file_service.upload_file(user_id, dir, mock_file, file_size)
        log_info("Upload file result", {"result": result})
        
        if result and 'error' in result:
            log_info("Upload file error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("File uploaded successfully")
        return result
    except Exception as e:
        log_error("Upload file endpoint error", e)
        raise


@router.get("/download")
async def download_file(
    dir: str,
    filename: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Download a file."""
    try:
        log_info("Download file request received", {"user_id": user_id, "dir": dir, "filename": filename})
        
        file_service = FileService(db)
        
        result = file_service.download(user_id, dir, filename)
        log_info("Download file result", {"result": result})
        
        if result and 'error' in result:
            log_info("Download file error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("File downloaded successfully")
        return FileResponse(path=result['real_path'], filename=result['filename'])
    except Exception as e:
        log_error("Download file endpoint error", e)
        raise


@router.delete("/delete")
async def delete_file(
    dir: str,
    filename: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Delete a file."""
    try:
        log_info("Delete file request received", {"user_id": user_id, "dir": dir, "filename": filename})
        
        file_service = FileService(db)
        
        result = file_service.delete(user_id, dir, filename)
        log_info("Delete file result", {"result": result})
        
        if result and 'error' in result:
            log_info("Delete file error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("File deleted successfully")
        return result
    except Exception as e:
        log_error("Delete file endpoint error", e)
        raise
