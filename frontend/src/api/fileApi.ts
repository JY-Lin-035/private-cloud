import { api } from './api';
import { API_BASE_URL } from '../config/api';

export const fileApi = {
  // Get file list
  list: async (parent_folder_uuid?: string) => {
    const response = await api.get('/api/files/list', {
      params: parent_folder_uuid ? { parent_folder_uuid } : {},
    });
    return response.data;
  },

  // Get storage info
  storage: async () => {
    const response = await api.get('/api/files/storage');
    return response.data;
  },

  // Download file
  download: async (file_uuid: string) => {
    const url = `${API_BASE_URL}/api/files/download?file_uuid=${file_uuid}&t=${Date.now()}`;
    const tempLink = document.createElement('a');
    tempLink.href = url;
    tempLink.download = 'download';
    document.body.appendChild(tempLink);
    tempLink.click();
    document.body.removeChild(tempLink);
  },

  // Delete file (soft or hard)
  delete: async (data: { file_uuid: string; permanent: boolean }) => {
    const response = await api.delete('/api/files/delete', { data });
    return response.data;
  },

  // Restore file
  restore: async (data: { file_uuid: string }) => {
    const response = await api.post('/api/files/restore', data);
    return response.data;
  },

  // Upload file (handled by Uppy directly)
  upload: async (formData: FormData) => {
    const response = await api.post('/api/files/uploadFile', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // List trash (soft-deleted files)
  trash: async () => {
    const response = await api.get('/api/files/trash');
    return response.data;
  },
};
