import { api } from './api';

export interface AuthedFlags {
  enable_file_preview: boolean;
}

export interface FileContent {
  text: string;
  size: number;
  updated_at: string;
  name: string;
  category: string;
}

let flagCache: AuthedFlags | null = null;
let inflight: Promise<AuthedFlags | null> | null = null;

export const previewApi = {
  authedFlags: async (refresh = false): Promise<AuthedFlags | null> => {
    if (flagCache && !refresh) return flagCache;
    if (!inflight) {
      inflight = api.get('/api/accounts/settings/features/authed')
        .then(r => {
          flagCache = r.data as AuthedFlags;
          inflight = null;
          return flagCache;
        })
        .catch(() => { inflight = null; return null; });
    }
    return inflight;
  },
  clearFlagCache: () => { flagCache = null; },

  createText: async (name: string, parent_folder_uuid?: string | null) => {
    const r = await api.post('/api/files/create', { name, parent_folder_uuid: parent_folder_uuid || null });
    return r.data as { uuid: string; name: string; size: number; updated_at: string; category: string };
  },

  content: async (uuid: string) => {
    const r = await api.get('/api/files/content', { params: { uuid } });
    return r.data as FileContent;
  },

  saveContent: async (uuid: string, text: string, if_updated_at: string | null) => {
    const r = await api.put('/api/files/content', { uuid, text, if_updated_at });
    return r.data as { uuid: string; size: number; updated_at: string };
  },

  previewToken: async (uuid: string) => {
    const r = await api.post('/api/files/previewToken', { uuid });
    return r.data as { token: string; ttl: number };
  },
};
