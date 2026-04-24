import { api } from './api';
import type { ShareLinkRequest, ShareLinkResponse, ShareListResponse } from '../types/index';

export const shareApi = {
  // Get share link
  getLink: async (data: ShareLinkRequest) => {
    const response = await api.post('/api/share/getLink', data);
    return response.data as ShareLinkResponse;
  },

  // Get share list
  getList: async () => {
    const response = await api.get('/api/share/getList');
    return response.data as ShareListResponse;
  },

  // Delete share link
  deleteLink: async (link: string) => {
    const response = await api.delete('/api/share/deleteLink', {
      params: { link },
    });
    return response.data;
  },
};
