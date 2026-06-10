import { api } from './api';
import type { ResetPasswordRequest, ModifyEmailRequest, ModifyPasswordRequest } from '../types/index';


export const accountApi = {
  // Get verification code
  getCode: async (data: { mode: string; email: string }) => {
    const response = await api.post('/api/accounts/getCode', data);
    return response.data;
  },

  // Reset password
  resetPassword: async (data: ResetPasswordRequest) => {
    const response = await api.put('/api/accounts/resetPW', data);
    return response.data;
  },

  // Modify email
  modifyMail: async (data: ModifyEmailRequest) => {
    const response = await api.put('/api/accounts/modifyMail', data);
    return response.data;
  },

  // Modify password
  modifyPW: async (data: ModifyPasswordRequest) => {
    const response = await api.put('/api/accounts/modifyPW', data);
    return response.data;
  },
};
