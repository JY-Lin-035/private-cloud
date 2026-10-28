/* MeowCloud media/preview service worker.
 * Intercepts same-origin /__media/<uid>/<uuid>?v=<updated_at>[&c=<ch>][&m=<mime>][&ptk=<t>]
 *   c absent -> media stream, cached in OPFS (Range aware)
 *   c=1      -> office PDF conversion (LibreOffice), cached
 *   c=2      -> ephemeral sandboxed raw (HTML/SVG) — never cached, opaque CSP, cookie-less
 * Cache purge on logout / 401 / account switch via {type:'media-purge'}.
 */
/* eslint-disable no-restricted-globals */
const swUrl = new URL(self.location.href);
const API_BASE = swUrl.searchParams.get('api') || '';
const MEDIA_PREFIX = '/__media/';
const ROOT = 'meow-media';
const SW_BUILD = 'p5-paced-11';

function trace0(k, stage) {
  broadcast({ type: 'media-skip', uid: k.uid, uuid: k.uuid, reason: `[w:${stage}]` });
}

async function broadcast(msg) {
  try {
    const cs = await self.clients.matchAll();
    cs.forEach((c) => c.postMessage(msg));
  } catch { /* noop */ }
}

function keyFor(pathname, search) {
  const parts = pathname.slice(MEDIA_PREFIX.length).split('/');
  if (parts.length !== 2) return null;
  const uid = parts[0], uuid = parts[1];
  const q = new URLSearchParams(search);
  const v = q.get('v') || '0';
  const mime = q.get('m') || '';
  const ch = q.get('c') || '';
  const ptk = q.get('ptk') || '';
  if (!/^[A-Za-z0-9._-]{1,80}$/.test(uid) || !/^[0-9a-fA-F-]{36}$/.test(uuid)) return null;
  const file = `${uuid}@${v}${ch ? '.' + ch : ''}.bin`;
  return { uid, uuid, file, v, mime, ch, ptk };
}

async function rootDir() {
  const base = await navigator.storage.getDirectory();
  return base.getDirectoryHandle(ROOT, { create: true });
}

async function dirFor(k, create = false) {
  return (await rootDir()).getDirectoryHandle(k.uid, { create });
}

async function fileHandle(k, create = false) {
  const d = await dirFor(k, create);
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

function pickHeaders(r) {
  const h = new Headers();
  for (const [hk, hv] of r.headers.entries()) {
    if (['content-type', 'content-length', 'content-range', 'accept-ranges', 'etag', 'cache-control'].includes(hk)) h.set(hk, hv);
  }
  if (!h.has('accept-ranges')) h.set('Accept-Ranges', 'bytes');
  h.set('Cache-Control', 'no-store');
  return h;
}

function rangeResponse(file, rangeHeader, k) {
  const size = file.size;
  const type = file.type || (k && k.mime) || 'application/octet-stream';
  const base = { 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };
  if (!rangeHeader) {
    return new Response(file, { status: 200, headers: { ...base, 'Content-Length': String(size), 'Content-Type': type } });
  }
  const m = /bytes=(\d*)-(\d*)/.exec(rangeHeader);
  if (!m) return new Response(file, { status: 200, headers: { ...base, 'Content-Length': String(size), 'Content-Type': type } });
  let start, end;
  if (m[1] === '') { start = Math.max(0, size - Number(m[2])); end = size - 1; }
  else { start = Number(m[1]); end = m[2] ? Math.min(Number(m[2]), size - 1) : size - 1; }
  if (start >= size || start > end) return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
  return new Response(file.slice(start, end + 1), {
    status: 206,
    headers: { ...base, 'Content-Length': String(end - start + 1), 'Content-Range': `bytes ${start}-${end}/${size}`, 'Content-Type': type },
  });
}

// Background cache warm: single-slot queue + pacing so it never starves
// playback or other API traffic through the (tunnel-bottlenecked) uplink.
const warmState = { running: false, pending: null, ctrl: null };

function abortWarmFor(uuid) {
  if (warmState.ctrl && warmState.running && warmState.pendingUuid === uuid) {
    try { warmState.ctrl.abort(); } catch { /* noop */ }
  }
}

async function warm(k) {
  if (k.ch === '2') return;
  if (warmState.running) { warmState.pending = k; warmState.pendingUuid = k.uuid; return; }
  warmState.running = true;
  warmState.pendingUuid = k.uuid;
  try { await doWarm(k); }
  finally {
    warmState.running = false;
    const next = warmState.pending;
    warmState.pending = null; warmState.pendingUuid = null;
    if (next) warm(next).catch(() => {});
  }
}

async function doWarm(k) {
  try {
    if (await cachedFile(k)) return;
    const upstream = k.ch === '1' ? '/api/files/convert' : '/api/files/stream';
    const ctrl = new AbortController();
    warmState.ctrl = ctrl;
    const full = await fetch(`${API_BASE}${upstream}?uuid=${k.uuid}`, { credentials: 'include', signal: ctrl.signal });
    if (!full.ok || !full.body) { trace0(k, 'fetch' + full.status); return; }
    const dir = await dirFor(k, true);
    const wipName = k.file + '.wip';
    const tmpH = await dir.getFileHandle(wipName, { create: true });
    try {
      const w = await tmpH.createWritable();
      const reader = full.body.getReader();
      let sinceCheck = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        await w.write(value);
        sinceCheck += value ? value.byteLength : 0;
        if (sinceCheck >= 262144) {           // throttle ~1.25MB/s; yield bandwidth to live traffic
          sinceCheck = 0;
          await new Promise(r => setTimeout(r, 200));
          const est = await navigator.storage.estimate();
          if (est.quota && est.usage > est.quota * 0.92) {
            await w.abort().catch(() => {});
            await dir.removeFile(wipName).catch(() => {});
            broadcast({ type: 'media-skip', uid: k.uid, uuid: k.uuid, reason: '空間接近上限，停止快取' });
            return;
          }
        }
      }
      await w.close();
      // atomic publish wip -> final (fallback copy if moveEntry unsupported)
      try { await dir.moveEntry(wipName, k.file); }
      catch {
        const finalH = await dir.getFileHandle(k.file, { create: true });
        const w2 = await finalH.createWritable();
        await (await tmpH.getFile()).stream().pipeTo(w2);
        await dir.removeFile(wipName).catch(() => {});
      }
      broadcast({ type: 'media-cached', uid: k.uid, uuid: k.uuid });
    } catch (err) {
      await dir.removeFile(wipName).catch(() => {});
      trace0(k, 'write:' + (err && err.name ? err.name : 'err'));
    } finally { warmState.ctrl = null; }
  } catch (e) {
    warmState.ctrl = null;
    if (e && e.name === 'AbortError') return;
    trace0(k, 'setup:' + (e && e.name ? e.name : 'err'));
  }
}

self.addEventListener('install', (e) => e.waitUntil(self.skipWaiting()));
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));

self.addEventListener('message', (e) => {
  const d = e.data || {};
  if (d.type === 'sw-ping') {
    e.waitUntil((async () => {
      const c = await self.clients.get(e.source && e.source.id);
      c && c.postMessage({ type: 'sw-pong', build: SW_BUILD });
    })());
  }
  if (d.type === 'media-purge') {
    e.waitUntil((async () => {
      try {
        const base = await navigator.storage.getDirectory();
        await base.removeEntry(ROOT, { recursive: true });
      } catch { /* nothing cached */ }
      const c = e.source && await self.clients.get(e.source.id);
      c && c.postMessage({ type: 'media-purged' });
    })());
  }
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(MEDIA_PREFIX)) return;
  const k = keyFor(url.pathname, url.search);
  if (!k) return;
  const trace = (stage) => broadcast({ type: 'media-skip', uid: k.uid, uuid: k.uuid, reason: `[${SW_BUILD}:${stage}]` });

  e.respondWith((async () => {
    // c=2: ephemeral sandbox raw preview — cookie-less, opaque, never cached
    if (k.ch === '2') {
      try {
        const r = await fetch(`${API_BASE}/api/files/raw?uuid=${k.uuid}&ptk=${encodeURIComponent(k.ptk)}`,
          { credentials: 'omit', cache: 'no-store' });
        const h = new Headers();
        h.set('Content-Type', k.mime || 'text/plain');
        h.set('Content-Security-Policy', 'sandbox allow-scripts');
        h.set('X-Content-Type-Options', 'nosniff');
        h.set('Cache-Control', 'no-store');
        return new Response(r.body, { status: r.status, headers: h });
      } catch {
        return new Response('preview unavailable', { status: 502 });
      }
    }
    let hit = null;
    try { hit = await cachedFile(k); } catch { /* miss */ }
    if (hit) return rangeResponse(hit, e.request.headers.get('range'), k);
    abortWarmFor(k.uuid);
    warm(k).catch(() => {});
    try {
      const headers = new Headers();
      for (const [hk, hv] of e.request.headers.entries()) {
        if (['range', 'accept-encoding', 'accept-language', 'sec-fetch-mode', 'sec-fetch-site', 'sec-fetch-dest'].includes(hk)) continue;
        headers.set(hk, hv);
      }
      const upstream = k.ch === '1' ? '/api/files/convert' : '/api/files/stream';
      const r = await fetch(`${API_BASE}${upstream}?uuid=${k.uuid}`, { headers, credentials: 'include', cache: 'no-store', mode: 'cors' });
      return new Response(r.body, { status: r.status, statusText: r.statusText, headers: pickHeaders(r) });
    } catch (err) {
      trace('fwd-err:' + err.name);
      return new Response(JSON.stringify({ detail: '閘道暫不可用' }), { status: 502, headers: { 'Content-Type': 'application/json' } });
    }
  })());
});
