import { api } from './api';

export interface SessionInfo {
  authenticated: boolean;
  id?: number;
  username?: string;
  email?: string;
  identity?: number;
}

let cached: SessionInfo | null = null;
let pending: Promise<SessionInfo> | null = null;

async function requestSession(): Promise<SessionInfo> {
  const response = await api.get('/api/accounts/checkSession');
  cached = response.data as SessionInfo;
  return cached;
}

function startRefresh(): Promise<SessionInfo> {
  if (!pending) {
    pending = requestSession().finally(() => { pending = null; });
  }
  return pending;
}

/** Cached-first session lookup: returns the last known value instantly
 *  (refreshing in the background), or awaits the in-flight/initial request. */
export async function getSession(): Promise<SessionInfo> {
  const inflight = startRefresh();
  if (cached) return cached;
  return inflight;
}

export function invalidateSessionCache() {
  cached = null;
}

// Prefetch as soon as this module loads (imported via authApi).
startRefresh().catch(() => { /* retried on demand */ });
