import { api } from './api';

export interface UserInfo {
  id: number;
  username: string;
  email: string;
  used_storage: number;
  total_storage: number;
  enabled: boolean;
  online: boolean;
}

export interface UserListResponse {
  users: UserInfo[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export const adminApi = {
  getUsers(page: number = 1, perPage: number = 10, search: string = ''): Promise<UserListResponse> {
      return api.get('/api/accounts/admin/users', { params: { page, per_page: perPage, search } }).then(r => r.data);
    },

    updateQuota(userId: number, totalStorage: number) {
      return api.put('/api/accounts/admin/users/' + userId + '/quota', null, { params: { total_storage: totalStorage } }).then(r => r.data);
    },

    forceLogout(userId: number) {
      return api.post('/api/accounts/admin/users/' + userId + '/force-logout').then(r => r.data);
    },

    toggleEnabled(userId: number) {
      return api.put('/api/accounts/admin/users/' + userId + '/toggle-enable').then(r => r.data);
    }
  };