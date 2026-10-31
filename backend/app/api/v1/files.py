from urllib.parse import quote
import base64
import secrets
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from redis import Redis
from app.schemas.file import (
    FileUploadRequest, DeleteFileRequest, RestoreFileRequest,
    FileListResponse, StorageInfoResponse, FileUploadResponse, FileDeleteResponse, FileRestoreResponse
)
from app.services.file_service import FileService
from app.services.folder_service import FolderService
from app.services import zip_service
from app.api.dependencies import get_db, get_redis, get_current_user_id, get_current_user_id_optional
from sqlalchemy import select
from app.api.rate_limit import rate_limit
from app.config import settings
from app.services import batch_ops
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


def _tus_location(request: Request, upload_id: str) -> str:
    """Absolute PATCH URL advertised to tus clients.

    Browsers refuse to send PATCH from an https page to an http URL (mixed
    content), and CSP connect-src blocks it too, so the scheme MUST be right.
    url_for() derives the scheme from uvicorn's view (http behind a plain-HTTP
    tunnel/proxy) and cloudflared does not always carry X-Forwarded-Proto, so
    we prefer the configured public API base (APP_URL) and otherwise infer
    HTTPS from Cloudflare markers on a loopback request.
    """
    base = (settings.APP_URL or "").strip().rstrip("/")
    if not base:
        scheme = request.url.scheme
        hdrs = request.headers
        proto = (hdrs.get("x-forwarded-proto") or "").split(",")[0].strip()
        if proto in ("http", "https"):
            scheme = proto
        elif hdrs.get("cf-connecting-ip") or '"https"' in (hdrs.get("cf-visitor") or ""):
            # Any request through the Cloudflare edge terminates TLS as https.
            scheme = "https"
        host = hdrs.get("host") or request.url.netloc
        base = f"{scheme}://{host}"
    return f"{base}/api/files/tus/{upload_id}"


@router.options("/tus")
async def tus_options():
    """Return tus handshake headers for browser clients."""
    return Response(
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
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id),
):
    """Create a new tus upload session and respond with the initial offset."""
    batch_ops.assert_not_deleting(redis, x_parent_folder_uuid)
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
        if file_size < 0:
            raise HTTPException(status_code=400, detail='Invalid Upload-Length')

        parent_uuid = x_parent_folder_uuid or None
        relative_path = metadata.get('relative_path')
        if relative_path and '/' in relative_path:
            folder_service = FolderService(db)
            resolved = folder_service.resolve_or_create_path(user_id, parent_uuid, relative_path.rsplit('/', 1)[0])
            if 'error' in resolved:
                raise HTTPException(status_code=resolved['stateCode'], detail=resolved['error'])
            parent_uuid = resolved['uuid'] or parent_uuid

        file_service = FileService(db)
        result = file_service.create_tus_upload(user_id, parent_uuid, filename, file_size)
        if result and 'error' in result:
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        upload_id = result['upload_id']
        location = str(_tus_location(request, upload_id))
        body = await request.body()
        if body:
            offset_result = file_service.append_tus_chunk(upload_id, 0, body, user_id)
            if offset_result and 'error' in offset_result:
                raise HTTPException(status_code=offset_result['stateCode'], detail=offset_result['error'])
        elif file_size == 0:
            finalize_result = file_service.finalize_tus_upload(upload_id, user_id)
            if finalize_result and 'error' in finalize_result:
                raise HTTPException(status_code=finalize_result['stateCode'], detail=finalize_result['error'])

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

        if not upload_offset:
            raise HTTPException(status_code=400, detail='Missing Upload-Offset header')

        file_service = FileService(db)
        result = file_service.append_tus_chunk(upload_id, int(upload_offset), body, user_id)
        if result and 'error' in result:
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        response_headers = {
            'Tus-Resumable': '1.0.0',
            'Upload-Offset': str(result['offset']),
            'Location': str(_tus_location(request, upload_id)),
        }
        if result.get('completed'):
            finalize_result = file_service.finalize_tus_upload(upload_id, user_id)
            if finalize_result and 'error' in finalize_result:
                raise HTTPException(status_code=finalize_result['stateCode'], detail=finalize_result['error'])
            response_headers['Upload-Complete'] = 'true'

        return Response(
            status_code=204,
            headers=response_headers,
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
        result = file_service.get_tus_upload(upload_id, user_id)
        if result and 'error' in result:
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        return JSONResponse(
            status_code=200,
            headers={
                'Tus-Resumable': '1.0.0',
                'Upload-Offset': str(result['offset']),
                'Upload-Length': str(result['file_size']),
                'Location': str(_tus_location(request, upload_id)),
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
        result = file_service.finalize_tus_upload(upload_id, user_id)
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
        logger.info(f"Get file list ok for user {user_id}")
        
        if result and 'error' in result:
            logger.error(f"Get file list error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        return result
    except Exception as e:
        logger.error(f"Get file list endpoint error: {e}")
        raise


@router.post("/uploadFile", dependencies=[Depends(rate_limit(30, 300))])
async def upload_file(
    file: UploadFile = File(...),
    parent_folder_uuid: str = Form(None),
    relative_path: str = Form(None),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Upload a file."""
    batch_ops.assert_not_deleting(redis, parent_folder_uuid)
    try:
        logger.info(f"Upload file request received, user_id: {user_id}, parent_folder_uuid: {parent_folder_uuid}, relative_path: {relative_path}, filename: {file.filename}")
        
        if relative_path and '/' in relative_path:
            folder_service = FolderService(db)
            resolved = folder_service.resolve_or_create_path(user_id, parent_folder_uuid, relative_path.rsplit('/', 1)[0])
            if 'error' in resolved:
                raise HTTPException(status_code=resolved['stateCode'], detail=resolved['error'])
            parent_folder_uuid = resolved['uuid'] or parent_folder_uuid
        
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
    batch_ops.assert_not_deleting(redis, file_uuid)
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
    batch_ops.assert_not_deleting(redis, file_uuid)
    try:
        file_service = FileService(db)
        actual_user_id = user_id

        if token:
            redis_key = f"download_file_token:{token}"
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
                actual_user_id = int(parts[0])
            except ValueError:
                raise HTTPException(status_code=401, detail="Invalid or expired download token")
            # Token is bound to the exact file it was issued for.
            if parts[1] != file_uuid:
                raise HTTPException(status_code=403, detail="Token does not match file")

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
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Delete a file (soft or hard)."""
    batch_ops.assert_not_deleting(redis, request.file_uuid)
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
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Restore a soft-deleted file."""
    batch_ops.assert_not_deleting(redis, request.file_uuid)
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
        return {**result, 'retention_days': settings.TRASH_RETENTION_DAYS}
    except Exception as e:
        logger.error("List trash files endpoint error", e)
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


class BatchDeleteRequest(BaseModel):
    folders: list[str] = Field(default_factory=list, max_length=2000)
    files: list[str] = Field(default_factory=list, max_length=2000)
    mode: str  # soft | permanent | restore


@router.post("/batchDelete")
async def batch_delete(
    request: BatchDeleteRequest,
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id),
):
    """One-shot batch trash op with per-item deletion locks (423 while running)."""
    return batch_ops.batch_operation(user_id, request.folders, request.files, request.mode, redis)


class FileMoveRequest(BaseModel):
    file_uuids: list[str] = Field(max_length=2000)
    target_folder_uuid: Optional[str] = None
    target_path: Optional[str] = None


class BulkDownloadRequest(BaseModel):
    file_uuids: list[str] = Field(default_factory=list, max_length=2000)
    folder_uuids: list[str] = Field(default_factory=list, max_length=400)


@router.post("/move")
async def move_files(
    request: FileMoveRequest,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Move files to an existing folder or a (auto-created) nested path."""
    batch_ops.assert_not_deleting(redis, *request.file_uuids, request.target_folder_uuid)
    target = request.target_folder_uuid
    if not target and request.target_path:
        resolved = FolderService(db).resolve_or_create_path(user_id, None, request.target_path)
        if 'error' in resolved:
            raise HTTPException(status_code=resolved['stateCode'], detail=resolved['error'])
        target = resolved['uuid']
    if not target:
        raise HTTPException(status_code=400, detail='需要提供目標資料夾或路徑')

    result = FileService(db).move_files(user_id, request.file_uuids, target)
    if result and 'error' in result:
        raise HTTPException(status_code=result['stateCode'], detail=result['error'])
    logger.info(f"Moved {len(result['moved'])} files for user {user_id} -> {target}; renamed={result['renamed']}")
    return result


@router.post("/downloadBulk")
async def download_bulk(
    request: BulkDownloadRequest,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Stream multiple selected files/folders as one zip archive."""
    batch_ops.assert_not_deleting(redis, *request.file_uuids, *request.folder_uuids)
    if not request.file_uuids and not request.folder_uuids:
        raise HTTPException(status_code=400, detail='沒有選擇任何項目')

    items, kept_files, kept_folders = zip_service.collect_zip_items(
        db, user_id, request.file_uuids[:1000], request.folder_uuids[:200]
    )
    logger.info(f"Bulk zip for user {user_id}: {kept_files} files, {kept_folders} folders, {len(items)} entries")
    return zip_service.build_zip_response(items, 'meowcloud-download')


# ================= preview / create / edit (P1) =================
import os as _os
import uuid as _uuid
from datetime import datetime as _dt

from app.models.account import Account
from app.models.file import File as FileModel
from app.models.folder import Folder as FolderModel
from app.services.feature_flag_service import is_feature_enabled
from app.utils.file_classes import MAX_EDIT_BYTES, classify, is_editable
from app.utils.name_validation import validate_display_name
from app.utils.pathing import unique_name


def _require_preview_flag():
    if not is_feature_enabled("enable_file_preview", default=False):
        raise HTTPException(status_code=403, detail="檔案預覽功能尚未啟用")


def _fmt_dt(dt) -> str:
    return dt.isoformat() if isinstance(dt, _dt) else str(dt)


def _load_editable(db: Session, user_id: int, file_uuid: str) -> FileModel:
    f = db.execute(
        select(FileModel).where(FileModel.uuid == file_uuid, FileModel.owner_id == user_id)
    ).scalar_one_or_none()
    if f is None or f.deleted_at is not None or not is_editable(f.name):
        raise HTTPException(status_code=404, detail="檔案不存在或不支援編輯")
    return f


class CreateFileRequest(BaseModel):
    name: str
    parent_folder_uuid: Optional[str] = None


class SaveContentRequest(BaseModel):
    uuid: str
    text: str
    if_updated_at: Optional[str] = None


@router.post("/create", dependencies=[Depends(rate_limit(20, 300))])
async def create_text_file(
    request: CreateFileRequest,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id),
):
    """Create a new empty editable text file in the given folder."""
    _require_preview_flag()
    cleaned, err = validate_display_name(request.name)
    if err:
        raise HTTPException(status_code=400, detail=err)
    if not is_editable(cleaned):
        raise HTTPException(status_code=400, detail="僅支援建立文字/代碼類檔案")
    parent_uuid = request.parent_folder_uuid or None
    if parent_uuid:
        parent = db.execute(
            select(FolderModel).where(FolderModel.uuid == parent_uuid, FolderModel.owner_id == user_id)
        ).scalar_one_or_none()
        if parent is None or parent.deleted_at is not None:
            raise HTTPException(status_code=404, detail="父資料夾不存在")
        batch_ops.assert_not_deleting(redis, parent_uuid)
        taken = set(db.execute(
            select(FileModel.name).where(
                FileModel.parent_folder_id == parent_uuid, FileModel.deleted_at.is_(None))
        ).scalars().all())
    else:
        taken = set(db.execute(
            select(FileModel.name).where(
                FileModel.owner_id == user_id,
                FileModel.parent_folder_id.is_(None), FileModel.deleted_at.is_(None))
        ).scalars().all())
    name = unique_name(cleaned, taken)
    file_uuid = str(_uuid.uuid4())
    storage_path = _os.path.join(settings.STORAGE_BASE_PATH, file_uuid)
    try:
        with open(storage_path, "wb"):
            pass
    except OSError:
        raise HTTPException(status_code=500, detail="無法建立檔案")
    import mimetypes
    mime = mimetypes.guess_type(name)[0] or "text/plain"
    row = FileModel(uuid=file_uuid, owner_id=user_id, parent_folder_id=parent_uuid,
                    name=name, size=0, mime_type=mime, storage_path=storage_path)
    db.add(row)
    db.commit()
    logger.info(f"Text file created uuid={file_uuid} by user {user_id}")
    return {"uuid": file_uuid, "name": name, "size": 0,
            "updated_at": _fmt_dt(row.updated_at), "category": classify(name)}


@router.get("/content", dependencies=[Depends(rate_limit(60, 60))])
async def get_file_content(
    uuid: str,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id),
):
    """Read a text-class file's content for the editor."""
    _require_preview_flag()
    f = _load_editable(db, user_id, uuid)
    if f.size and f.size > MAX_EDIT_BYTES:
        raise HTTPException(status_code=413, detail="檔案超過編輯上限 2MB，請下載後編輯")
    path = _os.path.join(settings.STORAGE_BASE_PATH, f.uuid)
    if not _os.path.isfile(path):
        raise HTTPException(status_code=404, detail="檔案內容不存在")
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        raise HTTPException(status_code=500, detail="讀取失敗")
    return {"text": raw.decode("utf-8", "replace"), "size": f.size,
            "updated_at": _fmt_dt(f.updated_at), "name": f.name, "category": classify(f.name)}


@router.put("/content", dependencies=[Depends(rate_limit(30, 60))])
async def save_file_content(
    request: SaveContentRequest,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id),
):
    """Write editor content back atomically with quota accounting and 409 conflict guard."""
    _require_preview_flag()
    batch_ops.assert_not_deleting(redis, request.uuid)
    f = _load_editable(db, user_id, request.uuid)
    if request.if_updated_at is not None and request.if_updated_at != _fmt_dt(f.updated_at):
        raise HTTPException(status_code=409, detail="檔案已被其他位置更新")
    data = request.text.encode("utf-8")
    if len(data) > MAX_EDIT_BYTES:
        raise HTTPException(status_code=413, detail="內容超過編輯上限 2MB")
    delta = len(data) - (f.size or 0)
    if delta > 0:
        acct = db.query(Account).filter(Account.id == user_id).with_for_update().first()
        if acct is None:
            raise HTTPException(status_code=404, detail="帳號不存在")
        if len(data) > acct.signal_file_size:
            raise HTTPException(status_code=413, detail="超過單檔大小上限")
        if (acct.used_size or 0) + delta > acct.total_file_size:
            raise HTTPException(status_code=413, detail="空間不足，無法儲存")
        acct.used_size = (acct.used_size or 0) + delta
    elif delta < 0:
        acct = db.query(Account).filter(Account.id == user_id).with_for_update().first()
        if acct:
            acct.used_size = max(0, (acct.used_size or 0) + delta)
    path = _os.path.join(settings.STORAGE_BASE_PATH, f.uuid)
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            _os.fsync(fh.fileno())
        _os.replace(tmp, path)
    except OSError:
        try:
            if _os.path.exists(tmp):
                _os.remove(tmp)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail="寫入失敗")
    f.size = len(data)
    f.updated_at = _dt.utcnow()
    db.commit()
    if f.parent_folder_id and delta:
        FolderService(db)._update_parent_folder_size(f.parent_folder_id, delta)
    logger.info(f"Content saved uuid={f.uuid} user={user_id} delta={delta}")
    return {"uuid": f.uuid, "size": f.size, "updated_at": _fmt_dt(f.updated_at)}


# ================= media stream with Range support (P2) =================
import re as _re
from fastapi.responses import StreamingResponse

from app.utils.file_classes import is_streamable

_STREAM_CHUNK = 64 * 1024
_RANGE_RE = _re.compile(r'bytes=(\d*)-(\d*)$')


def _load_streamable(db: Session, user_id: int, file_uuid: str) -> FileModel:
    f = db.execute(
        select(FileModel).where(FileModel.uuid == file_uuid, FileModel.owner_id == user_id)
    ).scalar_one_or_none()
    if f is None or f.deleted_at is not None or not is_streamable(f.name):
        raise HTTPException(status_code=404, detail="檔案不存在或不支援串流")
    path = _os.path.join(settings.STORAGE_BASE_PATH, f.uuid)
    if not _os.path.isfile(path):
        raise HTTPException(status_code=404, detail="檔案內容不存在")
    return f


@router.get("/stream", dependencies=[Depends(rate_limit(300, 60))])
async def stream_file(
    request: Request,
    uuid: str,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id),
):
    """Authenticated Range-capable inline stream for media/pdf (single range).

    Download/session accounting and throttle classification live in the
    middleware layer (stream-aware), keeping one source of truth here.
    """
    _require_preview_flag()
    batch_ops.assert_not_deleting(redis, uuid)
    f = _load_streamable(db, user_id, uuid)
    path = _os.path.join(settings.STORAGE_BASE_PATH, f.uuid)
    size = _os.path.getsize(path)
    etag = f'"{f.uuid}-{int(f.updated_at.timestamp()) if f.updated_at else 0}"'
    mime = f.mime_type or "application/octet-stream"
    base_headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'",
    }

    range_hdr = request.headers.get("range")
    start, end = 0, size - 1
    status = 200
    if range_hdr:
        m = _RANGE_RE.match(range_hdr.strip())
        if not m:
            raise HTTPException(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        s, e = m.group(1), m.group(2)
        if s == "" and e == "":
            raise HTTPException(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        if s == "":  # suffix range bytes=-N
            length = int(e)
            if length == 0:
                raise HTTPException(status_code=416, headers={"Content-Range": f"bytes */{size}"})
            start = max(0, size - min(length, size))
            end = size - 1
        else:
            start = int(s)
            end = int(e) if e else size - 1
            end = min(end, size - 1)
        if start >= size or start > end:
            raise HTTPException(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        status = 206

    length = end - start + 1

    def reader():
        with open(path, "rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(_STREAM_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    headers = dict(base_headers)
    headers["Content-Length"] = str(length)
    headers["Content-Type"] = mime
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return StreamingResponse(reader(), status_code=status, headers=headers, media_type=mime)
