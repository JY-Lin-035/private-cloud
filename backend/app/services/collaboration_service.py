from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from app.models.account import Account
from app.models.file import File
from app.models.collaboration import Collaboration
from app.repositories.collaboration_repository import CollaborationRepository
from app.repositories.file_repository import FileRepository
from app.repositories.account_repository import AccountRepository
from app.constants import HTTPStatus


class CollaborationService:
    def __init__(self, db: Session):
        self.db = db
        self.collab_repo = CollaborationRepository(db)
        self.file_repo = FileRepository(db)
        self.account_repo = AccountRepository(db)

    def add_collaborator(
        self,
        file_uuid: str,
        owner_id: int,
        collaborator_name: str,
        collaborator_email: str,
        permission: str = "editor"
    ) -> Optional[Dict[str, Any]]:
        """Add a collaborator to a file."""
        try:
            # 1. Verify file exists and belongs to the inviter
            file = self.file_repo.get_by_uuid(file_uuid)
            if not file:
                return {'error': '檔案不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            if file.owner_id != owner_id:
                return {'error': '你不是這個檔案的擁有者', 'stateCode': HTTPStatus.FORBIDDEN}

            # 2. Find the collaborator by name and/or email
            # Support formats: "name", "email", "name/email"
            search_name = collaborator_name
            search_email = collaborator_email

            # If name contains /, split it
            if '/' in collaborator_name:
                parts = collaborator_name.split('/', 1)
                search_name = parts[0].strip()
                if not search_email:
                    search_email = parts[1].strip()

            # If name looks like an email, use it as email (ignore the email field)
            if '@' in search_name:
                search_email = search_name
                search_name = ''

            collaborator = None
            if search_name:
                collaborator = self.account_repo.get_by_field('name', search_name)
            if not collaborator and search_email:
                collaborator = self.account_repo.get_by_field('email', search_email)
            if not collaborator:
                return {'error': '找不到符合名稱與 Email 的使用者', 'stateCode': HTTPStatus.NOT_FOUND}
            if collaborator.id == owner_id:
                return {'error': '不能邀請自己', 'stateCode': HTTPStatus.BAD_REQUEST}

            # 3. Check if already invited
            existing = self.collab_repo.get_by_file_and_collaborator(file_uuid, collaborator.id)
            if existing:
                return {'error': '該使用者已經在共編名單中', 'stateCode': HTTPStatus.BAD_REQUEST}

            # 4. Create collaboration record
            collab = Collaboration(
                file_uuid=file_uuid,
                owner_id=owner_id,
                collaborator_id=collaborator.id,
                permission=permission
            )
            self.collab_repo.create(collab)

            return {
                'message': '邀請成功',
                'data': {
                    'id': collab.id,
                    'file_uuid': collab.file_uuid,
                    'collaborator_id': collab.collaborator_id,
                    'collaborator_name': collaborator.name,
                    'collaborator_email': collaborator.email,
                    'permission': collab.permission,
                    'created_at': collab.created_at.isoformat()
                },
                'stateCode': HTTPStatus.OK
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}

    def remove_collaborator(
        self,
        file_uuid: str,
        owner_id: int,
        collaborator_id: int
    ) -> Optional[Dict[str, Any]]:
        """Remove a collaborator from a file."""
        try:
            # Verify the inviter owns the file
            file = self.file_repo.get_by_uuid(file_uuid)
            if not file or file.owner_id != owner_id:
                return {'error': '你沒有權限移除成員', 'stateCode': HTTPStatus.FORBIDDEN}

            removed = self.collab_repo.remove_by_file_and_collaborator(file_uuid, collaborator_id)
            if not removed:
                return {'error': '找不到該共編記錄', 'stateCode': HTTPStatus.NOT_FOUND}

            return {'message': '已移除共編成員', 'stateCode': HTTPStatus.OK}
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}

    def get_owned_collaborations(self, owner_id: int) -> Optional[Dict[str, Any]]:
        """Get all collaborations initiated by the current user (inviter view)."""
        try:
            collabs = self.collab_repo.get_by_owner(owner_id)
            # Group by file_uuid
            file_groups: Dict[str, Dict] = {}
            for c in collabs:
                file = self.file_repo.get_by_uuid(c.file_uuid)
                collaborator = self.account_repo.get_by_id(c.collaborator_id)
                file_uuid = c.file_uuid
                if file_uuid not in file_groups:
                    file_groups[file_uuid] = {
                        'file_uuid': file_uuid,
                        'file_name': file.name if file else '未知檔案',
                        'members': []
                    }
                file_groups[file_uuid]['members'].append({
                    'collaborator_id': c.collaborator_id,
                    'collaborator_name': collaborator.name if collaborator else '未知',
                    'collaborator_email': collaborator.email if collaborator else '未知',
                    'permission': c.permission,
                    'created_at': (c.created_at + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M')
                })
            items = list(file_groups.values())
            return {'items': items, 'total': len(items), 'stateCode': HTTPStatus.OK}
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}

    def get_my_collaborations(self, collaborator_id: int) -> Optional[Dict[str, Any]]:
        """Get all collaborations where user is invited (invitee view)."""
        try:
            collabs = self.collab_repo.get_by_collaborator(collaborator_id)
            items = []
            for c in collabs:
                file = self.file_repo.get_by_uuid(c.file_uuid)
                owner = self.account_repo.get_by_id(c.owner_id)
                items.append({
                    'id': c.id,
                    'file_uuid': c.file_uuid,
                    'file_name': file.name if file else '未知檔案',
                    'owner_id': c.owner_id,
                    'owner_name': owner.name if owner else '未知',
                    'owner_email': owner.email if owner else '未知',
                    'permission': c.permission,
                    'created_at': c.created_at.isoformat()
                })
            return {'items': items, 'total': len(items), 'stateCode': HTTPStatus.OK}
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}