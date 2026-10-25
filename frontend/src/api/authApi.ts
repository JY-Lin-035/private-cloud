import { api } from './api';
import type { LoginRequest, RegisterRequest } from '../types/index';
import { getSession, invalidateSessionCache } from './sessionCache';

export const authApi = {
  // Login
  login: async (data: LoginRequest) => {
    const response = await api.post('/api/accounts/login', data);
    invalidateSessionCache();
    await getSession().catch(() => { /* next call refreshes */ });
    return response.data;
  },

  // Register
  register: async (data: RegisterRequest) => {
    const response = await api.post('/api/accounts/register', data);
    return response.data;
  },

  // Check session (cached-first via sessionCache prefetch)
  checkSession: async (): Promise<any> => {
    return getSession();
  },

  // Sign out
  signOut: async () => {
    const response = await api.post('/api/accounts/signOut');
    invalidateSessionCache();
    return response.data;
  },

  // Get verification code
  getCode: async (data: { mode: 'mail' | 'pw'; email: string }) => {
    const response = await api.post('/api/accounts/getCode', data);
    return response.data;
  },

  // Public feature flags for login/register pages
  getPublicSettings: async (): Promise<{ allow_registration: boolean; enable_verification_email: boolean }> => {
    const { fetchPublicFlags } = await import('./publicFlags');
    return fetchPublicFlags();
  }
};
