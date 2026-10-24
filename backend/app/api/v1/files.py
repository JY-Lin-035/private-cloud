from urllib.parse import quote
import base64
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from redis import Redis
from app.schemas.file import (
    FileUploadRequest, DeleteFileRequest, RestoreFileRequest,
    FileListResponse, StorageInfoResponse, FileUploadResponse, FileDeleteResponse, FileRestoreResponse
)
from app.services.file_service import FileService
from app.api.dependencies import get_db, get_redis, get_current_user_id, get_current_user_id_optional
from app.config import settings
from app.utils import logger as log

router = APIRouter(prefix="/api/files", tags=["files"])
logger = log.get_logger("files_api.log")


def _decode_tus_metadata(metadata_header: Optional[str]) -> dict:
    """Decode the Upload-Metadata tus header into a dict."""
    metadata = {}
    if not metadata_header:
        return metadata

    parts = metadata_header.split()
    for idx in range(0, len(parts), 2):
        key = parts[idx]
        value = parts[idx + 1] if idx + 1 < len(parts) else ''
        try:
            metadata[key] = base64.b64decode(value).decode('utf-8')
        except Exception:
            metadata[key] = value

    return metadata


@router.options("/tus")
async def tus_options():
    """Return tus handshake headers for browser clients."""
    return JSONResponse(
        status_code=204,
        headers={
            'Tus-Resumable': '1.0.0',
            'Tus-Version': '1.0.0,1.0.2,1.0.3',
        },
    )


@router.post("/tus")
async def tus_create_upload(
    request: Request,
    upload_metadata: str = Header(None, alias='Upload-Metadata'),
    upload_length: str = Header(None, alias='Upload-Length'),
    tus_resumable: str = Header(None, alias='Tus-Resumable'),
    x_parent_folder_uuid: str = Header(None, alias='X-Parent-Folder-Uuid'),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Create a new tus upload session and respond with the initial offset."""
    try:
        if not tus_resumable:
            raise HTTPException(status_code=400, detail='Missing Tus-Resumable header')

        metadata = _decode_tus_metadata(upload_metadata)
        filename = metadata.get('filename') or metadata.get('name')
        if not filename:
            filename = request.headers.get('X-File-Name')
        if not filename:
            raise HTTPException(status_code=400, detail='Missing filename metadata')

        file_size = int(upload_length or 0)
        if file_size <= 0:
            raise HTTPException(status_code=400, detail='Invalid Upload-Length')

        file_service = FileService(db)
        result = file_service.create_tus_upload(user_id, x_parent_folder_uuid, filename, file_size)
        if result and 'error' in result:
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        upload_id = result['upload_id']
        location = str(request.url_for('tus_patch_upload', upload_id=upload_id))
        body = await request.body()
        if body:
            offset_result = file_service.append_tus_chunk(upload_id, 0, body)
            if offset_result and 'error' in offset_result:
                raise HTTPException(status_code=offset_result['stateCode'], detail=offset_result['error'])

        return JSONResponse(
            status_code=201,
            headers={
                'Tus-Resumable': '1.0.0',
                'Upload-Offset': str(len(body) if body else 0),
                'Location': location,
            },
            content={
                'upload_id': upload_id,
                'offset': len(body) if body else 0,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tus create upload endpoint error: {e}")
        raise


@router.patch("/tus/{upload_id}")
async def tus_patch_upload(
    upload_id: str,
    request: Request,
    upload_offset: str = Header(None, alias='Upload-Offset'),
    tus_resumable: str = Header(None, alias='Tus-Resumable'),
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Append a chunk to an existing tus upload and update the offset."""
    try:
        if not tus_resumable:
            raise HTTPException(status_code=400, detail='Missing Tus-Resumable header')

        body = await request.body()
        if not body:
            raise HTTPException(status_code=400, detail='Missing chunk body')

        if not upload_offset:
            raise HTTPException(status_code=400, detail='Missing Upload-Offset header')

        file_service = FileService(db)
        result = file_service.append_tus_chunk(upload_id, int(upload_offset), body)
        if result and 'error' in result:
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        response_headers = {
            'Tus-Resumable': '1.0.0',
            'Upload-Offset': str(result['offset']),
            'Location': str(request.url_for('tus_patch_upload', upload_id=upload_id)),
        }
        if result.get('completed'):
            finalize_result = file_service.finalize_tus_upload(upload_id)
            if finalize_result and 'error' in finalize_result:
                raise HTTPException(status_code=finalize_result['stateCode'], detail=finalize_result['error'])
            response_headers['Upload-Complete'] = 'true'

        return JSONResponse(
            status_code=204,
            headers=response_headers,
            content=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tus patch upload endpoint error: {e}")
        raise


@router.head("/tus/{upload_id}")
async def tus_head_upload(
    request: Request,
    upload_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Return the current tus offset for a resumable upload."""
    try:
        file_service = FileService(db)
        result = file_service.get_tus_upload(upload_id)
        if result and 'error' in result:
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        return JSONResponse(
            status_code=200,
            headers={
                'Tus-Resumable': '1.0.0',
                'Upload-Offset': str(result['offset']),
                'Upload-Length': str(result['file_size']),
                'Location': str(request.url_for('tus_patch_upload', upload_id=upload_id)),
            },
            content=None,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tus head upload endpoint error: {e}")
        raise


@router.post("/tus/{upload_id}/finish")
async def tus_finish_upload(
    upload_id: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Finalize a tus upload session and persist the final file."""
    try:
        file_service = FileService(db)
        result = file_service.finalize_tus_upload(upload_id)
        if result and 'error' in result:
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        return JSONResponse(
            status_code=200,
            headers={
                'Tus-Resumable': '1.0.0',
            },
            content=result,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tus finish upload endpoint error: {e}")
        raise


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


@router.get("/downloadToken")
async def get_download_token(
    file_uuid: str,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id),
):
    """Generate a short-lived token for cross-origin file download."""
    try:
        logger.info("Token req: {}/{}".format(user_id, file_uuid))
        file_service = FileService(db)
        result = file_service.download(user_id, file_uuid)
        if result and "error" in result:
            raise HTTPException(result["stateCode"], result["error"])
        token = secrets.token_hex(32)
        key = "download_file_token:{}".format(token)
        expire = settings.DOWNLOAD_TOKEN_EXPIRE_SECONDS
        redis.setex(key, expire, "{}:{}".format(user_id, file_uuid))
        return JSONResponse({
            "token": token,
            "file_uuid": file_uuid,
            "expires_in": expire,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Token gen err: %s" % e)
        raise


@router.get("/download")
async def download_file(
    file_uuid: str,
    token: str = Query(None),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: Optional[int] = Depends(get_current_user_id_optional)
):
    """Download a file."""
    try:
        file_service = FileService(db)
        actual_user_id = user_id

        if token:
            redis_key = f"download_file_token:{token}"
            tdata = redis.get(redis_key)
            if not tdata:
                raise HTTPException(status_code=401, detail="Invalid or expired download token")
            redis.delete(redis_key)
            tdata_str = tdata.decode() if isinstance(tdata, bytes) else tdata
            parts = tdata_str.split(":")
            if len(parts) != 2:
                raise HTTPException(status_code=400, detail="Invalid token data")
            actual_user_id = int(parts[0])

        if actual_user_id is None:
            raise HTTPException(status_code=401, detail="Authentication required")

        logger.info(f"Download file request received, user_id: {actual_user_id}, file_uuid: {file_uuid}")

        result = file_service.download(actual_user_id, file_uuid)
        logger.info(f"Download file result: {result}")

        if result and 'error' in result:
            logger.error(f"Download error: {result['error']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        logger.info("File downloaded successfully")
        encoded_filename = quote(result['filename'], safe='')
        return FileResponse(
            path=result['real_path'],
            filename=encoded_filename,
            media_type=result['mime_type'],
            headers={'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"}
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


@router.post("/recalculate-storage")
async def recalculate_storage(
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    """Recalculate used storage from actual non-deleted files."""
    try:
        logger.info(f"Recalculate storage request received, user_id: {user_id}")

        file_service = FileService(db)

        result = file_service.recalculate_used_storage(user_id)
        logger.info(f"Recalculate storage result: {result}")

        if result and 'error' in result:
            logger.error(f"Recalculate storage error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        logger.info("Storage recalculated successfully")
        return result
    except Exception as e:
        logger.error(f"Recalculate storage endpoint error: {e}")
        raise
