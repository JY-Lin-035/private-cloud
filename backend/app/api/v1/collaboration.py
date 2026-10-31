# Collaboration API endpoints
import secrets
from fastapi import APIRouter, Depends, HTTPException
from redis import Redis
from sqlalchemy.orm import Session
from app.api.dependencies import get_db, get_current_user_id, get_redis
from app.api.rate_limit import rate_limit
from app.config import settings
from app.schemas.collaboration import (
    CollaborationAddRequest,
    CollaborationRemoveRequest,
    WsTicketRequest,
)
from app.services.collaboration_service import CollaborationService
from app.constants import HTTPStatus

router = APIRouter(prefix="/api/collaboration", tags=["collaboration"])


@router.post("/wsTicket", dependencies=[Depends(rate_limit(30, 60))])
def issue_ws_ticket(
    body: WsTicketRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id),
):
    """Issue a short-lived, single-use ticket for a collaboration WebSocket.

    Delivered to the client as a Sec-WebSocket-Protocol value (never in the
    URL), consumed atomically with Redis GETDEL at handshake time.
    """
    from app.repositories.file_repository import FileRepository
    from app.repositories.collaboration_repository import CollaborationRepository

    file = FileRepository(db).get_by_uuid(body.file_uuid)
    if not file or file.deleted_at is not None:
        raise HTTPException(status_code=404, detail="檔案不存在")
    allowed = file.owner_id == user_id or \
        CollaborationRepository(db).get_by_file_and_collaborator(body.file_uuid, user_id) is not None
    if not allowed:
        raise HTTPException(status_code=403, detail="無權限存取此檔案")

    token = secrets.token_urlsafe(32)
    redis_client.setex(
        f"wsTicket:{token}",
        settings.WS_TICKET_TTL_SECONDS,
        f"{user_id}:{file.uuid}",
    )
    return {"ticket": token, "expires_in": settings.WS_TICKET_TTL_SECONDS}


@router.post("/addCollaborator", dependencies=[Depends(rate_limit(15, 60))])
def add_collaborator(
    request: CollaborationAddRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    service = CollaborationService(db)
    result = service.add_collaborator(
        file_uuid=request.file_uuid,
        owner_id=user_id,
        collaborator_name=request.collaborator_name,
        collaborator_email=request.collaborator_email
    )

    if result['stateCode'] != HTTPStatus.OK:
        raise HTTPException(status_code=result['stateCode'], detail=result['error'])

    return result


@router.delete("/removeCollaborator")
def remove_collaborator(
    request: CollaborationRemoveRequest,
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    service = CollaborationService(db)
    result = service.remove_collaborator(
        file_uuid=request.file_uuid,
        owner_id=current_user_id,
        collaborator_id=request.collaborator_id
    )

    if result['stateCode'] != HTTPStatus.OK:
        raise HTTPException(status_code=result['stateCode'], detail=result['error'])

    return result


@router.get("/ownedCollaborations")
def get_owned_collaborations(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Inviter: get all collaborations I initiated."""
    service = CollaborationService(db)
    result = service.get_owned_collaborations(current_user_id)

    if result['stateCode'] != HTTPStatus.OK:
        raise HTTPException(status_code=result['stateCode'], detail=result['error'])

    return result


@router.get("/myCollaborations")
def get_my_collaborations(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user_id)
):
    """Invitee: get all files shared with me."""
    service = CollaborationService(db)
    result = service.get_my_collaborations(current_user_id)

    if result['stateCode'] != HTTPStatus.OK:
        raise HTTPException(status_code=result['stateCode'], detail=result['error'])

    return result
