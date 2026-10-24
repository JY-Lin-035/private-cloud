import { api } from './api';
import type { LoginRequest, RegisterRequest } from '../types/index';

export const authApi = {
  // Login
  login: async (data: LoginRequest) => {
    const response = await api.post('/api/accounts/login', data);
    return response.data;
  },

  // Register
  register: async (data: RegisterRequest) => {
    const response = await api.post('/api/accounts/register', data);
    return response.data;
  },

  // Check session
  checkSession: async () => {
    const response = await api.get('/api/accounts/checkSession');
    return response.data;
  },

  // Sign out
  signOut: async () => {
    const response = await api.post('/api/accounts/signOut');
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
