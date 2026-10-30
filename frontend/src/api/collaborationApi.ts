import { api } from './api';

export const collaborationApi = {
  wsTicket: async (fileUuid: string) => {
    const response = await api.post('/api/collaboration/wsTicket', { file_uuid: fileUuid });
    return response.data as { ticket: string; expires_in: number };
  },

  addCollaborator(fileUuid: string, collaboratorName: string, collaboratorEmail: string) {
    return api.post('/api/collaboration/addCollaborator', {
      file_uuid: fileUuid,
      collaborator_name: collaboratorName,
      collaborator_email: collaboratorEmail,
    });
  },

  removeCollaborator(fileUuid: string, collaboratorId: number) {
    return api.delete('/api/collaboration/removeCollaborator', {
      data: { file_uuid: fileUuid, collaborator_id: collaboratorId },
    });
  },

  getOwnedCollaborations() {
    return api.get('/api/collaboration/ownedCollaborations');
  },

  getMyCollaborations() {
    return api.get('/api/collaboration/myCollaborations');
  },
};
