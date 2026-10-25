import { api } from './api';

export interface ControlRule {
  id: number;
  subject_type: 'ip' | 'ip_token' | 'user';
  ip_masked: string | null;
  token_prefix: string | null;
  username: string | null;
  action: 'slow' | 'block';
  scope: 'transfer' | 'full';
  direction: 'up' | 'down' | 'both';
  delay_ms: number;
  upload_kbps: number | null;
  download_kbps: number | null;
  reason: string | null;
  auto: boolean;
  created_at: string | null;
  expires_at: string | null;
  recent_accounts: string[];
}

export interface ScoreEntry { masked: string; score: number | string }

export const ipControlApi = {
  list: async (): Promise<{ rules: ControlRule[]; top_scores: ScoreEntry[] }> => {
    const r = await api.get('/api/ipcontrol/admin/list');
    return r.data;
  },

  create: async (data: Record<string, unknown>) => {
    const r = await api.post('/api/ipcontrol/admin', data);
    return r.data as { id: number };
  },

  update: async (id: number, data: Record<string, unknown>) => {
    const r = await api.put(`/api/ipcontrol/admin/${id}`, data);
    return r.data as { id: number };
  },

  remove: async (id: number) => {
    const r = await api.delete(`/api/ipcontrol/admin/${id}`);
    return r.data as { deleted: number };
  },

  suspendAccount: async (username: string) => {
    const r = await api.post('/api/ipcontrol/admin/suspend', { username });
    return r.data as { suspended: string };
  },

  hotlinks: async (ip: string): Promise<{ token: string; item: string; type: string; owner: string }[]> => {
    const r = await api.get('/api/ipcontrol/admin/hotlinks', { params: { ip } });
    return r.data.links as { token: string; item: string; type: string; owner: string }[];
  },
};
