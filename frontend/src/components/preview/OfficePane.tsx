import { useEffect, useState } from 'react';
import mammoth from 'mammoth/mammoth.browser';
import DOMPurify from 'dompurify';
import { API_BASE_URL } from '../../config/api';
import { mediaSrc } from '../../utils/mediaCache';

interface Props { uuid: string; filename: string; updatedAt: string; officeConvertEnabled: boolean; }

/** docx -> in-browser HTML via mammoth; other office -> LibreOffice PDF (if enabled). */
function OfficePane({ uuid, filename, updatedAt, officeConvertEnabled }: Props) {
  const isDocx = /\.docx$/i.test(filename);
  const [state, setState] = useState<'loading' | 'html' | 'pdf' | 'error'>('loading');
  const [html, setHtml] = useState('');
  const [pdfSrc, setPdfSrc] = useState('');
  const [err, setErr] = useState('');

  useEffect(() => {
    let live = true;
    if (isDocx) {
      // fetch docx bytes via the authenticated single-use download token flow
      fetch(`${API_BASE_URL}/api/files/downloadToken?file_uuid=${encodeURIComponent(uuid)}`, { credentials: 'include' })
        .then(async (r) => { if (!r.ok) throw new Error('下載憑證取得失敗'); return r.json(); })
        .then(async (j) => {
          const tok = j.token || j.url?.match(/token=([^&]+)/)?.[1];
          if (!tok) throw new Error('無下載憑證');
          const dl = await fetch(`${API_BASE_URL}/api/files/download?file_uuid=${encodeURIComponent(uuid)}&token=${encodeURIComponent(tok)}`, { credentials: 'include' });
          if (!dl.ok) throw new Error('下載失敗');
          return dl.arrayBuffer();
        })
        .then((buf) => mammoth.convertToHtml({ arrayBuffer: buf }))
        .then((res) => {
          if (!live) return;
          setHtml(DOMPurify.sanitize(res.value, { USE_PROFILES: { html: true }, FORBID_TAGS: ['style', 'script', 'iframe'], FORBID_ATTR: ['onerror', 'onload', 'onclick'] }));
          setState('html');
        })
        .catch((e: Error) => { if (live) { setErr(e.message); setState('error'); } });
    } else if (officeConvertEnabled) {
      // probe conversion status first (headers only) so 415/501/503 show as messages,
      // then let the iframe load through the SW (server-side disk cache makes it cheap)
      (async () => {
        try {
          const pr = await fetch(`${API_BASE_URL}/api/files/convert?uuid=${encodeURIComponent(uuid)}`,
            { credentials: 'include' });
          if (!pr.ok) {
            let detail = `轉換失败 (${pr.status})`;
            try { detail = (await pr.json()).detail || detail; } catch { /* keep */ }
            pr.body?.cancel().catch(() => {});
            if (live) { setErr(detail); setState('error'); }
            return;
          }
          pr.body?.cancel().catch(() => {});
          const u = await mediaSrc(uuid, 'cv-' + updatedAt, 'application/pdf', { conv: true });
          if (live) { setPdfSrc(u); setState('pdf'); }
        } catch (e) {
          if (live) { setErr((e as Error).message || '轉換暫不可用'); setState('error'); }
        }
      })();
    } else {
      setErr('Office 伺服器端預覽未啟用，請改用下載。');
      setState('error');
    }
    return () => { live = false; };
  }, [uuid, isDocx, officeConvertEnabled, updatedAt]);

  if (state === 'loading') return <div className="h-full grid place-items-center text-gray-400">轉換中，可能需數秒…</div>;
  if (state === 'error') return <div className="h-full grid place-items-center text-red-400 p-6 text-center">{err}</div>;
  if (state === 'html') return <div className="h-full overflow-auto bg-white"><article className="md-preview p-6 text-gray-900" dangerouslySetInnerHTML={{ __html: html }} /></div>;
  return <div className="h-full bg-black"><iframe title={filename} src={pdfSrc} className="w-full h-full min-h-[70vh] border-0" /></div>;
}

export default OfficePane;
