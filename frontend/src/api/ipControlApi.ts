import { api } from './api';

export interface ControlRule {
  id: number;
  subject_type: 'ip' | 'ip_token' | 'user';
  ip_masked: string | null;
  token_prefix: string | null;
  username: string | null;
  action: 'slow' | 'block';
  scope: 'transfer' | 'full' | 'stream';
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

  ipActorsByRule: async (ruleId: number): Promise<{ user_id: number; username: string; last_seen: string }[]> => {
    const r = await api.get('/api/ipcontrol/admin/ipactors', { params: { rule_id: ruleId } });
    return r.data.accounts as { user_id: number; username: string; last_seen: string }[];
  },

  ipActors: async (ip: string): Promise<{ user_id: number; username: string; last_seen: string }[]> => {
    const r = await api.get('/api/ipcontrol/admin/ipactors', { params: { ip } });
    return r.data.accounts as { user_id: number; username: string; last_seen: string }[];
  },

  // --- 風控門檻（版本化判定標準），與上面的「規則」是兩件事 ---
  policies: async (): Promise<{ version: number; groups: PolicyGroup[] }> => {
    const r = await api.get('/api/ipcontrol/admin/policies');
    return r.data;
  },

  policyHistory: async (): Promise<PolicyVersion[]> => {
    const r = await api.get('/api/ipcontrol/admin/policies/history', { params: { limit: 50 } });
    return r.data.history as PolicyVersion[];
  },

  updatePolicies: async (body: { changes: Record<string, number>; expected_version: number; reason?: string }) => {
    const r = await api.put('/api/ipcontrol/admin/policies', body);
    return r.data as { version: number; changed: Record<string, PolicyChange> };
  },

  resetPolicies: async (body: { ids: string[]; expected_version: number; reason?: string }) => {
    const r = await api.post('/api/ipcontrol/admin/policies/reset', body);
    return r.data as { version: number; changed: Record<string, PolicyChange> };
  },

  rollbackPolicy: async (body: { to_version: number; expected_version: number; reason?: string }) => {
    const r = await api.post('/api/ipcontrol/admin/policies/rollback', body);
    return r.data as { version: number; rolled_back_to: number };
  },
};

export interface PolicyItem {
  id: string;
  label: string;
  group: string;
  value: number;
  source: '程式預設' | '部署設定' | '管理員覆寫';
  code_default: number;
  deployment_value: number;
  unit: string;
  subject: string;
  window: string;
  window_seconds: number | null;
  window_editable: boolean;
  action: string;
  editable: boolean;
  allow_zero: boolean;
  min: number;
  max: number;
  route: string | null;
  method: string | null;
  depends: string;
  note: string;
}

export interface PolicyGroup { name: string; items: PolicyItem[] }

export interface PolicyChange { before: number; after: number; label: string }

export interface PolicyVersion {
  version: number;
  created_at: string;
  actor: string | null;
  reason: string | null;
  action: 'update' | 'reset' | 'rollback';
  changed: Record<string, PolicyChange>;
}
