// True once THIS document is controlled by the media SW (active alone is not
// enough — iframe subresource requests only route through an controlling SW).
export async function swControlsDocument(): Promise<boolean> {
  if (!('serviceWorker' in navigator)) return false;
  if (navigator.serviceWorker.controller) return true;
  const ok = await registerMediaSW();
  if (!ok) return false;
  if (navigator.serviceWorker.controller) return true;
  return new Promise((res) => {
    const t = setTimeout(() => res(!!navigator.serviceWorker.controller), 3000);
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      clearTimeout(t);
      res(true);
    }, { once: true });
  });
}

// Client glue for the /__media service worker (P2 media cache).
import { API_BASE_URL } from '../config/api';

type CacheEv = { type: string; uid?: string; uuid: string; reason?: string };
type Listener = (ev: CacheEv) => void;
const listeners = new Set<Listener>();
let registered = false;
let registeredOk = false;
let inflight: Promise<boolean> | null = null;

let uidCache: string | null = null;

// Per-account OPFS namespace. The session email is masked by the API, so we
// derive a filesystem-safe stable token from it (also avoids storing PII in
// file names). Full purge still happens on logout/401/account-switch.
export async function currentUid(): Promise<string> {
  if (uidCache) return uidCache;
  const e = localStorage.getItem('email') || 'anon';
  try {
    const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(e));
    uidCache = Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 24);
  } catch {
    uidCache = 'u' + (e.replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 40) || 'anon');
  }
  return uidCache;
}

export async function registerMediaSW(): Promise<boolean> {
  if (inflight) return inflight;
  if (registered) return registeredOk;
  registered = true;
  if (!('serviceWorker' in navigator) || !navigator.storage?.getDirectory) {
    registeredOk = false;
    return false;
  }
  inflight = (async () => {
    try {
      const url = `/meow-sw.js?api=${encodeURIComponent(API_BASE_URL)}&s=${__BUILD_TS__}`;
      await navigator.serviceWorker.register(url, { scope: '/' });
      await navigator.serviceWorker.ready;
      navigator.serviceWorker.addEventListener('message', (e) => {
        const d = e.data as CacheEv;
        if (d && (d.type === 'media-cached' || d.type === 'media-skip' || d.type === 'sw-pong')) {
          listeners.forEach((l) => l(d));
        }
      });
      try { if (navigator.storage.persist) await navigator.storage.persist(); } catch { /* noop */ }
      registeredOk = true;
    } catch (e) {
      console.warn('[mediaCache] SW register failed:', e);
      registeredOk = false;
    } finally {
      inflight = null;
    }
    return registeredOk;
  })();
  return inflight;
}

export async function mediaSrc(uuid: string, updatedAt: string, mime?: string): Promise<string> {
  const uid = await currentUid();
  const v = encodeURIComponent((updatedAt || '0').replace(/[^0-9A-Za-z:-]/g, ''));
  const m = mime ? `&m=${encodeURIComponent(mime)}` : '';
  return `/__media/${uid}/${uuid}?v=${v}${m}`;
}

declare global { interface Window { __swTrace?: string[] } }

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
