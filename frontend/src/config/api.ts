export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

function toWebSocketBaseUrl(url: string): string {
  if (!url) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}`;
  }
  return url.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
}

export const WS_BASE_URL = (import.meta.env.VITE_WS_BASE_URL || toWebSocketBaseUrl(API_BASE_URL)).replace(/\/$/, '');
