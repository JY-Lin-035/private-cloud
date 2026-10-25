import { api } from './api';

export interface AnnouncementRow {
  id: number;
  content: string;
  enabled: boolean;
  effective: boolean;
  expired: boolean;
  expires_at: string | null;
  created_at: string | null;
}

export const announcementApi = {
  active: async (): Promise<string[]> => {
    const r = await api.get('/api/announcements');
    return r.data.announcements as string[];
  },

  adminList: async (): Promise<AnnouncementRow[]> => {
    const r = await api.get('/api/announcements/admin/list');
    return r.data.announcements as AnnouncementRow[];
  },

  create: async (data: { content: string; expires_at?: string | null; enabled?: boolean }) => {
    const r = await api.post('/api/announcements/admin', data);
    return r.data as { id: number };
  },

  update: async (id: number, data: { content?: string; expires_at?: string | null; enabled?: boolean }) => {
    const r = await api.put(`/api/announcements/admin/${id}`, data);
    return r.data as { id: number };
  },

  remove: async (id: number) => {
    const r = await api.delete(`/api/announcements/admin/${id}`);
    return r.data as { deleted: number };
  },
};
