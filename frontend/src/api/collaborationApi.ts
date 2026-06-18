import { api } from './api';

export const collaborationApi = {
  addCollaborator(fileUuid: string, collaboratorName: string, collaboratorEmail: string) {
    return api.post('/collaboration/addCollaborator', {
      file_uuid: fileUuid,
      collaborator_name: collaboratorName,
      collaborator_email: collaboratorEmail,
    });
  },

  removeCollaborator(fileUuid: string, collaboratorId: number) {
    return api.delete('/collaboration/removeCollaborator', {
      data: { file_uuid: fileUuid, collaborator_id: collaboratorId },
    });
  },

  getOwnedCollaborations() {
    return api.get('/collaboration/ownedCollaborations');
  },

  getMyCollaborations() {
    return api.get('/collaboration/myCollaborations');
  },
};