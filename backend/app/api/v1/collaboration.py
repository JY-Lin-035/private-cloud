# Collaboration API endpoints
import traceback
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.dependencies import get_db, get_current_user_id
from app.schemas.collaboration import (
    CollaborationAddRequest,
    CollaborationRemoveRequest,
)
from app.services.collaboration_service import CollaborationService
from app.constants import HTTPStatus

router = APIRouter(prefix="/api/collaboration", tags=["collaboration"])


@router.post("/addCollaborator")
def add_collaborator(
    request: CollaborationAddRequest,
    db: Session = Depends(get_db),
    user_id: int = Depends(get_current_user_id)
):
    print(f"add_collaborator called: file_uuid={request.file_uuid}, name={request.collaborator_name}, email={request.collaborator_email}, user_id={user_id}")
    service = CollaborationService(db)
    result = service.add_collaborator(
        file_uuid=request.file_uuid,
        owner_id=user_id,
        collaborator_name=request.collaborator_name,
        collaborator_email=request.collaborator_email
    )

    print(f"add_collaborator result: {result}")
    if result['stateCode'] != HTTPStatus.OK:
        print(f"ERROR in add_collaborator: {result.get('error')}")
        traceback.print_exc()
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
