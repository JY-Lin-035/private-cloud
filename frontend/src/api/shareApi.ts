import { api } from './api';
import type { ShareListResponse } from '../types/index';

export const shareApi = {
  // Get share link
  getLink: async (data: { item_uuid: string; item_type: string }) => {
    const response = await api.post('/api/share/getLink', data);
    return response.data as string;
  },

  // Get share list
  getList: async () => {
    const response = await api.get('/api/share/getList');
    return response.data as ShareListResponse;
  },

  // Download share file
  downloadShareFile: async (link: string) => {
    const response = await api.get('/api/share/downloadFile', {
      params: { link },
      responseType: 'blob',
    });
    return response.data as Blob;
  },

  // Delete share link
  deleteLink: async (item_uuid: string, item_type: string) => {
    const response = await api.delete('/api/share/deleteLink', {
      params: { item_uuid: item_uuid.trim(), item_type: item_type.trim() },
    });
    return response.data;
  },
};
