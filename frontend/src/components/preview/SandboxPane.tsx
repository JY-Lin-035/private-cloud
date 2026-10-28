import { useEffect, useState } from 'react';
import { previewApi } from '../../api/previewApi';
import { mediaSrc } from '../../utils/mediaCache';

interface Props { uuid: string; filename: string; updatedAt?: string; }

/**
 * Renders HTML/SVG in a hard-sandboxed iframe. The document is fetched from
 * the /raw endpoint with a short-lived single-file token (never the session
 * cookie) and served with `CSP: sandbox` (opaque origin). We also pin the
 * iframe sandbox attribute to empty (no scripts, no same-origin) so previewed
 * markup can never reach the app, its cookies, or storage.
 */
const MIME_BY_EXT: Record<string, string> = { html: 'text/html', htm: 'text/html', xhtml: 'application/xhtml+xml', svg: 'image/svg+xml' };

function SandboxPane({ uuid, filename, updatedAt }: Props) {
  const [src, setSrc] = useState<string>('');
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    previewApi.previewToken(uuid)
      .then(async (t) => {
        const ext = (filename.split('.').pop() || '').toLowerCase();
        const mime = MIME_BY_EXT[ext] || 'text/plain';
        const url = await mediaSrc(uuid, updatedAt || 'sb', mime, { sandbox: true, ptk: t.token });
        if (live) setSrc(url);
      })
      .catch((e: Error) => { if (live) setErr(e.message); });
    return () => { live = false; };
  }, [uuid]);

  if (err) return <div className="h-full grid place-items-center text-red-400">{err}</div>;
  if (!src) return <div className="h-full grid place-items-center text-gray-400">載入中…</div>;
  return (
    <div className="h-full w-full bg-white">
      {/* sandbox="" => no scripts, no same-origin; backend also sends CSP sandbox */}
      <iframe title={filename} src={src} sandbox="" referrerPolicy="no-referrer"
        className="w-full h-full min-h-[70vh] border-0 bg-white" />
    </div>
  );
}

export default SandboxPane;
