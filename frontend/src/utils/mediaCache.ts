// Client glue for the /__media service worker (P2 media cache).
import { API_BASE_URL } from '../config/api';

type CacheEv = { type: string; uid?: string; uuid: string; reason?: string };
type Listener = (ev: CacheEv) => void;
const listeners = new Set<Listener>();
let registered = false;
let registeredOk = false;

export function currentUid(): string {
  // per-account isolation (defense-in-depth; full purge happens on logout/401)
  const e = localStorage.getItem('email') || 'anon';
  return encodeURIComponent(e).replace(/%/g, '').slice(0, 80) || 'anon';
}

export async function registerMediaSW(): Promise<boolean> {
  if (registered) return registeredOk;
  registered = true;
  if (!('serviceWorker' in navigator) || !navigator.storage?.getDirectory) {
    registeredOk = false;
    return false;
  }
  try {
    const url = `/sw.js?api=${encodeURIComponent(API_BASE_URL)}`;
    await navigator.serviceWorker.register(url, { scope: '/' });
    await navigator.serviceWorker.ready;
    navigator.serviceWorker.addEventListener('message', (e) => {
      const d = e.data as CacheEv;
      if (d && (d.type === 'media-cached' || d.type === 'media-skip')) {
        listeners.forEach((l) => l(d));
      }
    });
    // request persistent storage so cache survives eviction up to disk limits
    try { if (navigator.storage.persist) await navigator.storage.persist(); } catch { /* noop */ }
    registeredOk = true;
  } catch {
    registeredOk = false;
  }
  return registeredOk;
}

export function mediaSrc(uuid: string, updatedAt: string): string {
  const uid = currentUid();
  const v = encodeURIComponent((updatedAt || '0').replace(/[^0-9A-Za-z:-]/g, ''));
  return `/__media/${uid}/${uuid}?v=${v}`;
}

export function onMediaCacheEvent(fn: Listener): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

// Clear all OPFS media cache (logout / 401 / account switch). Fire-and-forget.
export function purgeMediaCache(): void {
  try {
    navigator.serviceWorker?.ready
      .then((reg) => reg.active?.postMessage({ type: 'media-purge' }))
      .catch(() => { /* noop */ });
  } catch { /* noop */ }
}
