import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../../config/api';
import { extOf } from '../../utils/fileClass';
import { fileApi } from '../../api/fileApi';

interface Props { uuid: string; filename: string; size: number; }

type Kind = 'docx' | 'pptx' | 'odp' | 'odt' | 'pdf' | null;

const KIND_BY_EXT: Record<string, Kind> = {
  docx: 'docx', pptx: 'pptx', odp: 'odp', odt: 'odt', pdf: 'pdf',
};
const MAX_RENDER_BYTES = 80 * 1024 * 1024;

const HOST_STYLES = `html,body{margin:0;padding:0;background:#fff;color:#111;font-family:system-ui,-apple-system,"Noto Sans TC",sans-serif}
html,body,#stage{height:100%}
#stage{padding:0;max-width:none;margin:0 auto;overflow:auto;display:block}
#stage.pptx-mode{overflow:auto;display:flex;align-items:center;justify-content:center}
.pdf-page{display:block;width:calc(100% - 32px);max-width:960px;margin:16px auto;border:1px solid #ddd;border-radius:4px;box-shadow:0 1px 6px rgba(0,0,0,.08);height:auto}
.pdf-more{text-align:center;color:#888;font-size:13px;padding:12px}
.docx-body p{margin:.6em 0;line-height:1.7}.docx-body h1,.docx-body h2,.docx-body h3{margin:1em 0 .5em}
.docx-body table{border-collapse:collapse}.docx-body td,.docx-body th{border:1px solid #ccc;padding:4px 8px}
.docx-body img{max-width:100%;height:auto}
.slide-card{border:1px solid #ddd;border-radius:10px;padding:24px 28px;margin:18px 0;min-height:200px;background:#fdfdfd;box-shadow:0 1px 4px rgba(0,0,0,.06)}
.slide-no{font-size:12px;color:#888;margin-bottom:10px}
.slide-text{margin:.45em 0;line-height:1.65}.pptx-stage{margin:0 auto;flex:none}`;

const API_ORIGIN = (() => {
  try {
    return new URL(API_BASE_URL, window.location.origin).origin;
  } catch {
    return window.location.origin;
  }
})();
const HOST_SRCDOC = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src blob: ${window.location.origin} ${API_ORIGIN}; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; media-src data: blob:; connect-src 'none'"><style>${HOST_STYLES}</style></head><body><div id="stage"></div><script src="/office/render.js?v=${__BUILD_TS__}"><\/script></body></html>`;



/**
 * Office preview WITHOUT any server parsing: bytes are fetched with the
 * authenticated single-use download token, then posted to /office/host.html
 * embedded with sandbox="allow-scripts" — an opaque origin: no cookies, no
 * parent DOM, meta-CSP kills network. A compromised parser is trapped there.
 */
function OfficeFrame({ uuid, filename, size }: Props) {
  const kind = KIND_BY_EXT[extOf(filename)] ?? null;
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [state, setState] = useState<'idle' | 'loading' | 'rendering' | 'ready' | 'error'>('idle');
  const [errMsg, setErrMsg] = useState('');
  const [stats, setStats] = useState('');
  const bytesRef = useRef<ArrayBuffer | null>(null);

  useEffect(() => {
    if (!kind) return;
    if (size > MAX_RENDER_BYTES) {
      setErrMsg('檔案過大，請下載查看');
      setState('error');
      return;
    }
    let live = true;
    (async () => {
      setState('loading');
      try {
        const tok = await fileApi.downloadToken(uuid);
        const token = (tok as any).token || (tok as any).url?.match(/token=([^&]+)/)?.[1];
        if (!token) throw new Error('下載憑證取得失敗');
        const r = await fetch(`${API_BASE_URL}/api/files/download?file_uuid=${encodeURIComponent(uuid)}&token=${encodeURIComponent(token)}`,
          { credentials: 'include' });
        if (!r.ok) throw new Error(`下載失敗 (${r.status})`);
        const buf = await r.arrayBuffer();
        if (!live) return;
        bytesRef.current = buf;
        setState('rendering');
      } catch (e) {
        if (live) { setErrMsg((e as Error).message); setState('error'); }
      }
    })();
    return () => { live = false; };
  }, [uuid, kind, size]);

  const readyRef = useRef(false);
  useEffect(() => {
    const onMsg = (ev: MessageEvent) => {
      if (ev.origin !== 'null' || ev.source !== iframeRef.current?.contentWindow) return;
      const d = ev.data as { type?: string; msg?: string; chars?: number; sample?: string; pages?: number } | null;
      if (!d) return;
      if (d.type === 'office-ready') {
        readyRef.current = true;
        if (bytesRef.current) {
          const elx = iframeRef.current!
          requestAnimationFrame(() => requestAnimationFrame(() => {
            elx.contentWindow?.postMessage(
              { type: 'office-render', kind, bytes: bytesRef.current!,
                width: elx.clientWidth || 900, height: elx.clientHeight || 560 }, '*')
          }))
        }
      } else if (d.type === 'office-ok') {
        setStats(d.pages ? `已渲染 ${d.pages} 頁` : `已渲染 ${d.chars ?? 0} 字`);
        setState('ready');
      } else if (d.type === 'office-err') {
        setErrMsg(d.msg || '渲染失敗');
        setState('error');
      }
    };
    window.addEventListener('message', onMsg);
    return () => { window.removeEventListener('message', onMsg); };
  }, [kind]);

  // bytes resolved before frame ready? push now
  useEffect(() => {
    if (state === 'rendering' && readyRef.current && bytesRef.current && iframeRef.current?.contentWindow) {
      iframeRef.current.contentWindow.postMessage(
        { type: 'office-render', kind, bytes: bytesRef.current,
          width: iframeRef.current.clientWidth, height: iframeRef.current.clientHeight }, '*');
    }
  }, [state, kind]);

  useEffect(() => {
    if (state !== 'rendering' && state !== 'ready') return;
    const guard = state === 'rendering'
      ? setTimeout(() => setState((x) => (x === 'rendering' ? 'error' : x)), 90000)
      : 0;
    const host = iframeRef.current
    let ro: ResizeObserver | null = null
    let last = { w: 0, h: 0 }
    const sendResize = () => {
      if (!host?.contentWindow || !readyRef.current || !bytesRef.current) return
      const w = host.clientWidth, h = host.clientHeight
      if (!w || !h || (Math.abs(w - last.w) < 24 && Math.abs(h - last.h) < 24)) return
      last = { w, h }
      host.contentWindow.postMessage({ type: 'office-resize', width: w, height: h }, '*')
    }
    try { ro = new ResizeObserver(() => sendResize()); if (host) ro.observe(host) } catch { /* unsupported */ }
    const iv = setInterval(sendResize, 1500)
    return () => { clearTimeout(guard); clearInterval(iv); ro?.disconnect() }
  }, [state]);

  if (!kind) {
    return <OfficeCard filename={filename} title="此 Office 格式暫不支援線上預覽" />;
  }
  if (state === 'error') {
    return <OfficeCard filename={filename} title={`預覽失敗：${errMsg || '渲染逾時'}`} />;
  }

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-1.5 bg-gray-800 text-gray-300 text-xs flex items-center gap-2 shrink-0">
        <span>🛡️ 沙箱渲染（檔案僅在隔離框架內解析，不經過伺服器）</span>
        <div className="flex-1" />
        {(state === 'loading' || state === 'rendering') && (
          <span className="text-cyan-300 animate-pulse">{state === 'loading' ? '載入中…' : '渲染中…'}</span>
        )}
        {state === 'ready' && <span className="text-green-400">✓ {stats}</span>}
      </div>
      <div className="flex-1 min-h-0 bg-white relative">
        <iframe ref={iframeRef} title={`office-${filename}`} srcDoc={HOST_SRCDOC}
          sandbox="allow-scripts" className="absolute inset-0 w-full h-full border-0" />
      </div>
    </div>
  );
}

function OfficeCard({ filename, title }: { filename: string; title: string }) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-3 text-gray-400 p-8 text-center">
      <div className="text-5xl">📄</div>
      <p className="text-lg">{title}</p>
      <p className="text-sm break-all max-w-md">{filename}</p>
      <p className="text-xs text-gray-500">請關閉後使用下載。</p>
    </div>
  );
}

export default OfficeFrame;
