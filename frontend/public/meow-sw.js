/* MeowCloud media/preview service worker.
 * Intercepts same-origin /__media/<uid>/<uuid>?v=<updated_at>[&c=<ch>][&m=<mime>][&ptk=<t>]
 *   c absent -> media stream, cached in OPFS (Range aware)
 * Cache purge on logout / 401 / account switch via {type:'media-purge'}.
 */
/* eslint-disable no-restricted-globals */
const swUrl = new URL(self.location.href);
const API_BASE = swUrl.searchParams.get('api') || '';
const MEDIA_PREFIX = '/__media/';
const ROOT = 'meow-media-2';
const LEGACY_ROOTS = ['meow-media'];
const SW_BUILD = 'p15-ttl-30m';
const CACHE_TTL_MS = 30 * 60 * 1000;   // drop entries untouched for 30 min
const ATIME_FILE = 'atimes.json';
const atimeMem = new Map();            // uid -> Map(uuid -> ms)
let atimeFlushTimer = null;
let lastSweep = 0;

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
  const mimeTag = mime ? '.' + mime.replace(/[^a-z0-9]+/gi, '').slice(0, 16) : '';
  const file = `${uuid}@${v}${ch ? '.' + ch : ''}${mimeTag}.bin`;
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
  const type = (k && k.mime) || file.type || 'application/octet-stream';
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

// Background cache warm: single-slot queue + pacing + pause/resume.
// media-stop (player closed) aborts the running warm but KEEPS the partial
// .wip so the next open resumes via Range; purge drops everything.
const warmState = { running: false, pending: null, ctrl: null, runningUuid: null, pendingUuid: null, abortReason: null };

function stopWarm(uuid) {
  if (warmState.pendingUuid === uuid) { warmState.pending = null; warmState.pendingUuid = null; }
  if (warmState.runningUuid === uuid && warmState.ctrl) {
    warmState.abortReason = 'pause';
    try { warmState.ctrl.abort(); } catch { /* noop */ }
  }
}

async function warm(k) {
  if (warmState.runningUuid === k.uuid || warmState.pendingUuid === k.uuid) return; // already fetching this one
  if (warmState.running) { warmState.pending = k; warmState.pendingUuid = k.uuid; return; }
  warmState.running = true;
  warmState.runningUuid = k.uuid;
  try { await doWarm(k); }
  finally {
    warmState.running = false;
    warmState.runningUuid = null;
    warmState.abortReason = null;
    const next = warmState.pending;
    warmState.pending = null; warmState.pendingUuid = null;
    if (next) warm(next).catch(() => {});
  }
}

async function publishWip(dir, wipName, finalName) {
  try { await dir.moveEntry(wipName, finalName); return; } catch { /* unsupported */ }
  const finalH = await dir.getFileHandle(finalName, { create: true });
  const w2 = await finalH.createWritable();
  await (await dir.getFileHandle(wipName)).getFile().then((f) => f.stream().pipeTo(w2));
  await dir.removeEntry(wipName).catch(() => {});
}

async function doWarm(k, allowRetry = true) {
  let dir = null;
  const wipName = k.file + '.wip';
  try {
    if (await cachedFile(k)) return;
    dir = await dirFor(k, true);
    let start = 0;
    try { const h0 = await dir.getFileHandle(wipName); start = (await h0.getFile()).size; } catch { /* fresh */ }
    const ctrl = new AbortController();
    warmState.ctrl = ctrl;
    const full = await fetch(`${API_BASE}/api/files/stream?uuid=${k.uuid}`, {
      credentials: 'include', signal: ctrl.signal,
      headers: start > 0 ? { Range: `bytes=${start}-` } : undefined,
    });
    let total = null;
    if (full.status === 206 && start > 0) {
      const m = /\/(\d+)\s*$/.exec(full.headers.get('content-range') || '');
      total = m ? Number(m[1]) : null;
      if (total != null && total <= start) { // partial already complete or stale-bigger
        if (total === start) { await publishWip(dir, wipName, k.file); broadcast({ type: 'media-cached', uid: k.uid, uuid: k.uuid }); }
        else { await dir.removeEntry(wipName).catch(() => {}); if (allowRetry) return doWarm(k, false); }
        return;
      }
    }
    if (!full.ok || !full.body) {
      if (full.status === 416 && start > 0 && allowRetry) { await dir.removeEntry(wipName).catch(() => {}); return doWarm(k, false); }
      trace0(k, 'fetch' + full.status); return;
    }
    const resume = full.status === 206 && start > 0;
    try { await navigator.storage.persist(); } catch { /* opt-in */ }
    const tmpH = await dir.getFileHandle(wipName, { create: true });
    let acc = 0;
    let w = null;
    try {
      if (resume) {
        try {
          w = await tmpH.createWritable({ keepExistingData: true });
          if (typeof w.seek === 'function') await w.seek(start);
          acc = start;
        } catch { acc = 0; w = await tmpH.createWritable(); } // no append support -> restart
      } else {
        w = await tmpH.createWritable();
      }
      const reader = full.body.getReader();
      let sincePace = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        await w.write(value);
        acc += value ? value.byteLength : 0;
        sincePace += value ? value.byteLength : 0;
        if (sincePace >= 262144) { sincePace = 0; await new Promise(r => setTimeout(r, 60)); } // ~4MB/s cap
      }
      await w.close();
      // total may be null for 200 responses; size verified implicitly by close
      if (total != null && acc !== total) throw new Error('size-mismatch');
      await publishWip(dir, wipName, k.file);
      markAccess(k);
      broadcast({ type: 'media-cached', uid: k.uid, uuid: k.uuid });
    } catch (err) {
      const aborted = (err && err.name === 'AbortError') || ctrl.signal.aborted;
      if (aborted && warmState.abortReason === 'pause') { // player closed: seal partial so bytes survive for resume
        try { if (w) await w.close(); } catch { /* stream unusable after abort */ }
        broadcast({ type: 'media-paused', uid: k.uid, uuid: k.uuid });
        return;
      }
      try { if (w) await w.close().catch(() => {}); } catch { /* noop */ }
      await dir.removeEntry(wipName).catch(() => {});
      if (aborted) return; // purge
      const name = err && err.name ? err.name : 'err';
      broadcast({ type: 'media-skip', uid: k.uid, uuid: k.uuid,
        reason: name === 'QuotaExceededError' ? '裝置空間不足，無法快取（仍可串流播放）' : '寫入失敗:' + name });
    } finally { warmState.ctrl = null; }
  } catch (e) {
    warmState.ctrl = null;
    if (e && e.name === 'AbortError') return;
    trace0(k, 'setup:' + (e && e.name ? e.name : 'err'));
  }
}

self.addEventListener('install', (e) => e.waitUntil(self.skipWaiting()));

// ------------------------------------------------------- access-time TTL
function markAccess(k) {
  try {
    let m = atimeMem.get(k.uid);
    if (!m) { m = new Map(); atimeMem.set(k.uid, m); }
    m.set(k.uuid, Date.now());
    if (!atimeFlushTimer) atimeFlushTimer = setTimeout(flushAtimes, 30000);
  } catch { /* best-effort */ }
}

async function flushAtimes() {
  atimeFlushTimer = null;
  const roots = [];
  try { const base = await navigator.storage.getDirectory(); await base.getDirectoryHandle(ROOT); roots.push(ROOT); } catch { /* none */ }
  for (const uid of atimeMem.keys()) {
    try {
      const dir = (await rootDir()).getDirectoryHandle(uid);
      const map = Object.fromEntries(atimeMem.get(uid) || []);
      const h = await dir.getFileHandle(ATIME_FILE, { create: true });
      const w = await h.createWritable();
      await w.write(JSON.stringify(map));
      await w.close();
    } catch { /* uid dir gone */ }
  }
}

async function sweepExpired(force = false) {
  const now = Date.now();
  if (!force && now - lastSweep < 60000) return 0;
  lastSweep = now;
  await flushAtimesSoon();
  let removed = 0;
  let base;
  try { base = await navigator.storage.getDirectory(); } catch { return 0; }
  let rootH;
  try { rootH = await base.getDirectoryHandle(ROOT); } catch { return 0; }
  for await (const [uid, dh] of rootH.entries()) {
    if (dh.kind !== 'directory') continue;
    let atimes = {};
    try { atimes = JSON.parse(await (await (await dh.getFileHandle(ATIME_FILE)).getFile()).text()) || {}; } catch { /* none */ }
    const mem = atimeMem.get(uid);
    let alive = 0;
    for await (const [name, fh] of dh.entries()) {
      if (fh.kind !== 'file' || name === ATIME_FILE) continue;
      const uuid = name.split('@')[0];
      let at = atimes[uuid] || 0;
      if (mem && mem.get(uuid) > at) at = mem.get(uuid);
      if (!at) { try { at = (await fh.getFile()).lastModified || 0; } catch { /* skip */ } }
      if (now - at > CACHE_TTL_MS) {
        try { await dh.removeEntry(name); removed++; } catch { /* busy */ }
      } else alive++;
    }
    if (alive === 0) { try { await rootH.removeEntry(uid); atimeMem.delete(uid); removed++; } catch { /* non-empty race */ } }
  }
  return removed;
}

async function flushAtimesSoon() {
  if (atimeFlushTimer) { clearTimeout(atimeFlushTimer); }
  await flushAtimes();
}
self.addEventListener('activate', (e) => e.waitUntil((async () => {
  for (const legacy of LEGACY_ROOTS) {
    try { const base = await navigator.storage.getDirectory(); await base.removeEntry(legacy, { recursive: true }); } catch { /* none */ }
  }
  await sweepExpired(true).catch(() => {});
  await self.clients.claim();
})()));

self.addEventListener('message', (e) => {
  const d = e.data || {};
  if (d.type === 'sw-ping') {
    e.waitUntil((async () => {
      const c = await self.clients.get(e.source && e.source.id);
      c && c.postMessage({ type: 'sw-pong', build: SW_BUILD });
    })());
  }
  if (d.type === 'media-stop') { stopWarm(d.uuid); return; }
  if (d.type === 'media-sweep') {
    e.waitUntil((async () => {
      const n = await sweepExpired(true).catch(() => 0);
      const c = e.source && await self.clients.get(e.source.id);
      c && c.postMessage({ type: 'media-swept', removed: n });
    })());
    return;
  }
  if (d.type === 'media-purge') {
    e.waitUntil((async () => {
      warmState.abortReason = 'purge';
      try { if (warmState.ctrl) warmState.ctrl.abort(); } catch { /* noop */ }
      atimeMem.clear();
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
  if (url.origin !== self.location.origin) return;
  // office host page: synthesized in-SW so nginx security headers can't block framing
  if (!url.pathname.startsWith(MEDIA_PREFIX)) return;
  const k = keyFor(url.pathname, url.search);
  if (!k) return;
  const trace = (stage) => broadcast({ type: 'media-skip', uid: k.uid, uuid: k.uuid, reason: `[${SW_BUILD}:${stage}]` });

  e.respondWith((async () => {
    let hit = null;
    try { hit = await cachedFile(k); } catch { /* miss */ }
    if (hit) {
      markAccess(k);
      sweepExpired().catch(() => {});
      broadcast({ type: 'media-cached', uid: k.uid, uuid: k.uuid });
      return rangeResponse(hit, e.request.headers.get('range'), k);
    }
    warm(k).catch(() => {});
    try {
      const headers = new Headers();
      for (const [hk, hv] of e.request.headers.entries()) {
        if (['accept-encoding', 'accept-language', 'sec-fetch-mode', 'sec-fetch-site', 'sec-fetch-dest'].includes(hk)) continue;
        headers.set(hk, hv);
      }
      const r = await fetch(`${API_BASE}/api/files/stream?uuid=${k.uuid}`, { headers, credentials: 'include', cache: 'no-store', mode: 'cors' });
      return new Response(r.body, { status: r.status, statusText: r.statusText, headers: pickHeaders(r) });
    } catch (err) {
      trace('fwd-err:' + err.name);
      return new Response(JSON.stringify({ detail: '閘道暫不可用' }), { status: 502, headers: { 'Content-Type': 'application/json' } });
    }
  })());
});
