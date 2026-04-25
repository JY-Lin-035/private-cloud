import { api } from './api';
import type { StorageResponse } from '../types/index';

export const storageApi = {
  // Get storage information
  getStorage: async () => {
    const response = await api.get('/api/files/getStorage');
    return response.data as StorageResponse;
  },
};
