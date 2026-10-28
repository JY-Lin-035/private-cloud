/* MeowCloud media cache service worker.
 * Intercepts same-origin /__media/<uid>/<uuid>?v=<updated_at> requests:
 *   hit  -> serve from OPFS (Range aware, zero network)
 *   miss -> pass through to the authenticated /api/files/stream endpoint and
 *           warm the FULL file into OPFS in the background (stream playback
 *           is never blocked by the cache write).
 * Cache purges on logout / 401 / account switch via {type:'media-purge'}.
 */
/* eslint-disable no-restricted-globals */
const swUrl = new URL(self.location.href);
const API_BASE = swUrl.searchParams.get('api') || '';
const MEDIA_PREFIX = '/__media/';
const ROOT = 'meow-media';

function keyFor(pathname, search) {
  // pathname: /__media/<uid>/<uuid> ; v param = file updated_at
  const parts = pathname.slice(MEDIA_PREFIX.length).split('/');
  if (parts.length !== 2) return null;
  const uid = parts[0], uuid = parts[1];
  const v = new URLSearchParams(search).get('v') || '0';
  if (!/^[^/]{1,128}$/.test(uid) || !/^[0-9a-fA-F-]{36}$/.test(uuid)) return null;
  return { uid, uuid, dir: `${ROOT}/${uid}`, file: `${uuid}@${v}.bin`, v };
}

async function rootDir() {
  const base = await navigator.storage.getDirectory();
  return base.getDirectoryHandle(ROOT, { create: true });
}

async function fileHandle(k, create = false) {
  const d = await (await rootDir()).getDirectoryHandle(k.dir, { create });
  return d.getFileHandle(k.file, { create });
}

async function cachedFile(k) {
  try {
    const h = await fileHandle(k, false);
    return await h.getFile();
  } catch {
    return null;
  }
}

function rangeResponse(file, rangeHeader) {
  const size = file.size;
  const type = file.type || 'application/octet-stream';
  const base = { 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };
  if (!rangeHeader) {
    return new Response(file, { status: 200, headers: { ...base, 'Content-Length': String(size), 'Content-Type': type } });
  }
  const m = /bytes=(\d*)-(\d*)/.exec(rangeHeader);
  if (!m) return new Response(file, { status: 200, headers: { ...base, 'Content-Length': String(size), 'Content-Type': type } });
  let start, end;
  if (m[1] === '') { start = Math.max(0, size - Number(m[2])); end = size - 1; }
  else { start = Number(m[1]); end = m[2] ? Math.min(Number(m[2]), size - 1) : size - 1; }
  if (start >= size || start > end) {
    return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
  }
  return new Response(file.slice(start, end + 1), {
    status: 206,
    headers: { ...base, 'Content-Length': String(end - start + 1),
               'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Type': type },
  });
}

async function broadcast(msg) {
  try {
    const cs = await self.clients.matchAll();
    cs.forEach((c) => c.postMessage(msg));
  } catch { /* noop */ }
}

async function warm(k) {
  try {
    if (await cachedFile(k)) return;
    const est = await navigator.storage.estimate();
    const quota = (est.quota || 0) - (est.usage || 0);
    const probe = await fetch(`${API_BASE}/api/files/stream?uuid=${k.uuid}`, { credentials: 'include' });
    if (!probe.ok) return;
    const total = Number(probe.headers.get('content-length') || 0);
    if (quota < total + 20 * 1024 * 1024) {
      broadcast({ type: 'media-skip', uid: k.uid, uuid: k.uuid, reason: '空間不足，僅串流' });
      return;
    }
    const full = await fetch(`${API_BASE}/api/files/stream?uuid=${k.uuid}`, { credentials: 'include' });
    if (!full.ok || !full.body) return;
    const h = await fileHandle(k, true);
    const w = await h.createWritable();
    await full.body.pipeTo(w);
    broadcast({ type: 'media-cached', uid: k.uid, uuid: k.uuid });
  } catch { /* best effort */ }
}

self.addEventListener('install', (e) => e.waitUntil(self.skipWaiting()));
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('message', (e) => {
  const d = e.data || {};
  if (d.type === 'media-purge') {
    e.waitUntil((async () => {
      try {
        const base = await navigator.storage.getDirectory();
        await base.removeEntry(ROOT, { recursive: true });
      } catch { /* nothing cached */ }
      const c = await self.clients.get(d.clientId);
      c && c.postMessage({ type: 'media-purged' });
    })());
  }
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(MEDIA_PREFIX)) return;
  const k = keyFor(url.pathname, url.search);
  if (!k) return;
  e.respondWith((async () => {
    const hit = await cachedFile(k);
    if (hit) return rangeResponse(hit, e.request.headers.get('range'));
    warm(k).catch(() => {});
    try {
      const r = await fetch(new Request(`${API_BASE}/api/files/stream?uuid=${k.uuid}`, {
        headers: e.request.headers, credentials: 'include',
      }));
      return r;
    } catch {
      return new Response('gateway off', { status: 502 });
    }
  })());
});
