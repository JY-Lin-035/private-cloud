import axios from 'axios';
import { API_BASE_URL } from '../config/api';

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Response interceptor for error handling
const publicPaths = ['/', '/forgetPassword', '/register'];
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      if (publicPaths.includes(window.location.pathname) && error.response?.data?.detail && error.response?.data?.detail !== "Unauthorized") {
        return Promise.reject(new Error(error.response?.data?.message ?? error.response?.data?.detail));
      }
      else if (!publicPaths.includes(window.location.pathname)) {
        // Unauthorized - clear localStorage and redirect to login
        localStorage.clear();
        window.location.href = '/';
      }
      else {
        return Promise.reject(new Error("發生未預期的錯誤請稍後再試"));
      }
    }

    const message =
      error.response?.status === 429 ? "請求過多，請稍後再試" :
        error.response?.status >= 500 ? "伺服器錯誤，請稍後再試" :
          error.response?.data?.detail ?? "發生錯誤，請稍後再試";

    return Promise.reject(new Error(message));
  }
);
