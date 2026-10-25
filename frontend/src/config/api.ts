export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';
export const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || '';

export function buildWebSocketUrl(path: string): string {
  const baseUrl = WS_BASE_URL || API_BASE_URL || window.location.origin;
  const base = new URL(baseUrl, window.location.origin);
  if (base.protocol === 'https:') {
    base.protocol = 'wss:';
  } else if (base.protocol === 'http:') {
    base.protocol = 'ws:';
  }
  const basePath = base.pathname.replace(/\/$/, '');
  return new URL(`${basePath}/${path.replace(/^\//, '')}`, base).toString();
}
