import { api } from './api';
import type { ShareLinkRequest, ShareListResponse } from '../types/index';

export const shareApi = {
  // Get share link
  getLink: async (data: ShareLinkRequest) => {
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
  deleteLink_by_filename: async (dir: string, fileName: string) => {
    const response = await api.delete('/api/share/deleteLink', {
      params: { dir: dir, filename: fileName },
    });
    return response.data;
  },

  deleteLink_by_link: async (link: string) => {
    const response = await api.delete('/api/share/deleteLink', {
      params: { link: link },
    });
    return response.data;
  },
};
