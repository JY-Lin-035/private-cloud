import { useEffect, useState } from 'react';
import { previewApi } from '../../api/previewApi';
import { fileApi } from '../../api/fileApi';

interface Props { uuid: string; filename: string; }

const META_CSP = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: blob:; style-src 'unsafe-inline'; media-src data: blob:; font-src data:;">`;

/**
 * HTML/SVG static preview. Parent fetches the document with a single-use,
 * cookie-less token, then renders it in a srcdoc frame: the parent CSP
 * (script-src self, no unsafe-inline) kills every inline/remote script inside,
 * the opaque frame cannot reach app data, and no service worker is required.
 */
function SandboxPane({ uuid, filename }: Props) {
  const [doc, setDoc] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const t = await previewApi.previewToken(uuid);
        const r = await fetch(`/api/files/raw?uuid=${encodeURIComponent(uuid)}&ptk=${encodeURIComponent(t.token)}`,
          { credentials: 'same-origin' });
        if (!r.ok) throw new Error(`載入失敗 (${r.status})`);
        const text = await r.text();
        if (live) setDoc(META_CSP + text);
      } catch (e) {
        if (live) setErr((e as Error).message);
      }
    })();
    return () => { live = false; };
  }, [uuid]);

  if (err) {
    return (
      <div className="h-full flex flex-col items-center justify-center gap-3 text-gray-400 p-8">
        <div className="text-4xl">🚫</div>
        <p>{err}</p>
        <button type="button" className="px-4 py-2 rounded bg-blue-600 text-white text-sm"
          onClick={() => fileApi.download(uuid)}>下載檔案</button>
      </div>
    );
  }
  if (doc === null) return <div className="h-full grid place-items-center text-gray-400">載入中…</div>;

  return (
    <div className="h-full flex flex-col">
      <div className="px-3 py-1.5 bg-amber-900/40 text-amber-300 text-xs border-b border-amber-800/50 shrink-0">
        🛡️ 沙箱預覽：以下為不受信任的檔案內容，腳本與外連已全部停用
      </div>
      <div className="flex-1 min-h-0 bg-white">
        <iframe title={filename} srcDoc={doc} sandbox="" referrerPolicy="no-referrer"
          className="w-full h-full min-h-[65vh] border-0 bg-white" />
      </div>
    </div>
  );
}

export default SandboxPane;
