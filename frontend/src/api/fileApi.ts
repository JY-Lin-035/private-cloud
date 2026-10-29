import { api } from './api';
import { API_BASE_URL } from '../config/api';

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

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

  downloadToken: async (file_uuid: string) => {
    const response = await api.get('/api/files/downloadToken', { params: { file_uuid } });
    return response.data as { token: string; file_uuid: string; expires_in: number };
  },

  // Download file
  download: async (file_uuid: string) => {
    const response = await api.get('/api/files/downloadToken', {
      params: { file_uuid },
    });
    const data = response.data;
    const url = `${API_BASE_URL}/api/files/download?file_uuid=${file_uuid}&token=${data.token}`;
    const tempLink = document.createElement('a');
    tempLink.href = url;
    tempLink.download = 'download';
    document.body.appendChild(tempLink);
    tempLink.click();
    document.body.removeChild(tempLink);
  },


  // Delete file (soft or hard)
  batchOp: async (data: { folders: string[]; files: string[]; mode: 'soft' | 'permanent' | 'restore' }) => {
    const response = await api.post('/api/files/batchDelete', data);
    return response.data as { folders: number; files: number; freed_bytes: number; skipped: { uuid: string; reason: string }[] };
  },
  delete: async (data: { file_uuid: string; permanent: boolean }) => {
    const response = await api.delete('/api/files/delete', { data });
    return response.data;
  },

  // Move files to an existing folder uuid or a (auto-created) nested path
  moveFiles: async (data: { file_uuids: string[]; target_folder_uuid?: string; target_path?: string }) => {
    const response = await api.post('/api/files/move', data);
    return response.data;
  },

  // Move folders
  moveFolders: async (data: { folder_uuids: string[]; target_folder_uuid?: string; target_path?: string }) => {
    const response = await api.post('/api/folders/move', data);
    return response.data;
  },

  // Download a folder as a streamed zip
  downloadFolderZip: async (folderUuid: string, folderName: string) => {
    const response = await api.get('/api/folders/download', {
      params: { folder_uuid: folderUuid },
      responseType: 'blob',
    });
    saveBlob(response.data as Blob, `${folderName}.zip`);
  },

  // Download multiple selected items as one zip
  downloadBulk: async (file_uuids: string[], folder_uuids: string[]) => {
    const response = await api.post('/api/files/downloadBulk', { file_uuids, folder_uuids }, { responseType: 'blob' });
    saveBlob(response.data as Blob, 'meowcloud-download.zip');
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
