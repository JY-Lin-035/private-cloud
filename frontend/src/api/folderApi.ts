import { api } from './api';
import type { CreateFolderRequest, RenameFolderRequest, DeleteResponse } from '../types/index';

export const folderApi = {
  // Create folder
  createFolder: async (data: CreateFolderRequest) => {
    const response = await api.post('/api/folders/createFolder', data);
    return response.data;
  },

  // Rename folder
  renameFolder: async (data: RenameFolderRequest) => {
    const response = await api.put('/api/folders/renameFolder', data);
    return response.data;
  },

  // Delete folder
  deleteFolder: async (dir: string, folderName: string) => {
    const response = await api.delete('/api/folders/deleteFolder', {
      params: { dir, folderName },
    });
    return response.data as DeleteResponse;
  },
};
