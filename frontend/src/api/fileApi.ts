import { api } from './api';
import type {
  FileListResponse,
  DeleteResponse,
  FileInfoResponse,
} from '../types/index';



export const fileApi = {
  // Get file list
  getFileList: async (path: string) => {
    const response = await api.get('/api/files/getFileList', {
      params: { path },
    });
    return response.data as FileListResponse;
  },

  // Get file info
  getFileInfo: async (link: string) => {
    const response = await api.get('/api/files/getFileInfo', {
      params: { link },
    });
    return response.data as FileInfoResponse;
  },

  // Download file
  downloadFile: async (dir: string, filename: string) => {
    const response = await api.get('/api/files/downloadFile', {
      params: { dir, filename },
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  },  

  // Delete file
  deleteFile: async (dir: string, filename: string) => {
    const response = await api.delete('/api/files/delete', {
      params: { dir, filename },
    });
    return response.data as DeleteResponse;
  },

  // Upload file (handled by Uppy directly)
  uploadFile: async (formData: FormData) => {
    const response = await api.post('/api/files/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },
};
