import { api } from './api';

export const folderApi = {
  // Create folder
  create: async (data: { parent_folder_uuid?: string; name: string }) => {
    const response = await api.post('/api/folders/create', data);
    return response.data;
  },

  // Rename folder
  rename: async (data: { folder_uuid: string; name: string }) => {
    const response = await api.put('/api/folders/rename', data);
    return response.data;
  },

  // Delete folder (soft or hard)
  delete: async (data: { folder_uuid: string; permanent: boolean }) => {
    const response = await api.delete('/api/folders/delete', { data });
    return response.data;
  },

  // Restore folder
  restore: async (data: { folder_uuid: string }) => {
    const response = await api.post('/api/folders/restore', data);
    return response.data;
  },

  // List folders by owner
  list: async () => {
    const response = await api.get('/api/folders/list');
    return response.data;
  },

  // List trash (soft-deleted folders)
  trash: async () => {
    const response = await api.get('/api/folders/trash');
    return response.data;
  },

  // Get user's Home folder
  getHome: async () => {
    const response = await api.get('/api/folders/home');
    return response.data;
  },

  // Get folder path/hierarchy
  getPath: async (folder_uuid: string) => {
    const response = await api.get('/api/folders/path', {
      params: { folder_uuid },
    });
    return response.data;
  },
};
