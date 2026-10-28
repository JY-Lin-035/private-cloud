import { useCallback, useEffect, useRef, useState } from 'react';
import { previewApi } from '../../api/previewApi';
import EditorPane from './EditorPane';
import MediaPane from './MediaPane';
import SandboxPane from './SandboxPane';
import OfficePane from './OfficePane';
import { classify, isStreamable } from '../../utils/fileClass';
import MarkdownPane from './MarkdownPane';
import JsonPane from './JsonPane';
import FallbackPane from './FallbackPane';

interface Props {
  uuid: string;
  filename: string;
  onClose: () => void;
  onSaved?: (meta: { uuid: string; size: number; updated_at: string }) => void;
}

type Status = { kind: 'idle' | 'saving' | 'saved' | 'error'; msg?: string };

function FileOpener({ uuid, filename, onClose, onSaved }: Props) {
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState<string>('other');
  const [text, setText] = useState('');
  const [baseline, setBaseline] = useState('');
  const [updatedAt, setUpdatedAt] = useState('');
  const [meta, setMeta] = useState<{ size: number } | null>(null);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const dirty = text !== baseline;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  const isMedia = isStreamable(filename);
  const localCat = classify(filename);
  const bypassContent = isMedia || localCat === 'docx' || localCat === 'office' || localCat === 'html' || localCat === 'svg';
  const [officeFlag, setOfficeFlag] = useState(false);

  useEffect(() => {
    previewApi.authedFlags().then((f) => setOfficeFlag(!!f?.enable_preview_office));
  }, []);

  useEffect(() => {
    let live = true;
    if (bypassContent) {
      setCategory(localCat);
      setUpdatedAt('v1');
      setLoading(false);
      return () => { live = false; };
    }
    setLoading(true);
    previewApi.content(uuid)
      .then((c) => {
        if (!live) return;
        setText(c.text);
        setBaseline(c.text);
        setCategory(c.category);
        setUpdatedAt(c.updated_at);
        setMeta({ size: c.size });
        setLoading(false);
      })
      .catch((e: Error & { status?: number }) => {
        if (!live) return;
        setStatus({ kind: 'error', msg: e.message });
        setLoading(false);
        setCategory('unavailable');
      });
    return () => { live = false; };
  }, [uuid, bypassContent, localCat, filename]);

  const save = useCallback(async () => {
    if (!dirtyRef.current) return;
    setStatus({ kind: 'saving' });
    try {
      const res = await previewApi.saveContent(uuid, text, updatedAt || null);
      setBaseline(text);
      setUpdatedAt(res.updated_at);
      setMeta({ size: res.size });
      setStatus({ kind: 'saved', msg: '已儲存' });
      onSaved?.(res);
      window.setTimeout(() => setStatus((s) => (s.kind === 'saved' ? { kind: 'idle' } : s)), 1500);
    } catch (e: unknown) {
      const err = e as Error & { status?: number };
      if (err.status === 409) {
        const overwrite = window.confirm('檔案已被其他位置更新。仍以您目前的內容覆蓋儲存？');
        if (overwrite) {
          try {
            const res = await previewApi.saveContent(uuid, text, null);
            setBaseline(text);
            setUpdatedAt(res.updated_at);
            setMeta({ size: res.size });
            setStatus({ kind: 'saved', msg: '已覆蓋儲存' });
            onSaved?.(res);
          } catch (e2: unknown) {
            setStatus({ kind: 'error', msg: (e2 as Error).message });
          }
        } else {
          setStatus({ kind: 'error', msg: '已取消儲存（您的內容仍保留在編輯器中）' });
        }
      } else {
        setStatus({ kind: 'error', msg: err.message });
      }
    }
  }, [uuid, text, updatedAt, onSaved]);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        void save();
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [save]);

  useEffect(() => {
    const beforeUnload = (e: BeforeUnloadEvent) => {
      if (dirtyRef.current) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, []);

  function attemptClose() {
    if (dirty && !window.confirm('尚有未儲存的修改，確定關閉？')) return;
    onClose();
  }

  const pane = () => {
    if (loading) return <div className="p-8 text-gray-400">載入中…</div>;
    if (category === 'unavailable') {
      return <FallbackPane filename={filename} message={status.msg} />;
    }
    if (category === 'markdown') {
      return <MarkdownPane filename={filename} value={text} onChange={setText} onSave={save} />;
    }
    if (category === 'json') {
      return <JsonPane filename={filename} value={text} onChange={setText} onSave={save} />;
    }
    if (['text', 'code', 'html', 'svg'].includes(category)) {
      return <EditorPane filename={filename} value={text} onChange={setText} onSave={save} />;
    }
    if (['image', 'video', 'audio', 'pdf'].includes(category)) {
      return <MediaPane uuid={uuid} filename={filename} updatedAt={updatedAt || 'v1'} size={meta?.size || 0} />;
    }
    if (category === 'html' || category === 'svg') {
      return <SandboxPane uuid={uuid} filename={filename} />;
    }
    if (category === 'docx' || category === 'office') {
      return <OfficePane uuid={uuid} filename={filename} updatedAt={updatedAt || 'v1'} officeConvertEnabled={officeFlag} />;
    }
    return <FallbackPane filename={filename} />;
  };

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70" role="dialog" aria-modal="true" aria-label={`編輯 ${filename}`}>
      <div className="w-[96vw] md:w-[92vw] h-[94vh] flex flex-col rounded-lg overflow-hidden bg-gray-900 border border-gray-700 shadow-2xl">
        <div className="flex items-center gap-3 px-4 py-2 bg-gray-800 border-b border-gray-700 shrink-0">
          <span className="font-medium text-gray-100 truncate" title={filename}>{filename}</span>
          {dirty && <span className="text-amber-400 text-xs shrink-0">● 未儲存</span>}
          {meta && !dirty && <span className="text-gray-500 text-xs shrink-0">{meta.size} bytes</span>}
          <span className={`text-xs shrink-0 ${status.kind === 'error' ? 'text-red-400' : 'text-green-400'}`}>
            {status.kind !== 'idle' && status.kind !== 'saving' ? status.msg : ''}
          </span>
          <div className="flex-1" />
          {status.kind === 'saving' && <span className="text-cyan-300 text-sm animate-pulse">儲存中…</span>}
          {!isMedia && !['html','svg','docx','office'].includes(category) && <button
            type="button"
            onClick={() => void save()}
            disabled={!dirty || status.kind === 'saving'}
            className="px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm shrink-0"
            title="Ctrl+S"
          >
            儲存
          </button>}
          <button
            type="button"
            onClick={attemptClose}
            className="px-3 py-1 rounded bg-gray-700 hover:bg-gray-600 text-gray-100 text-sm shrink-0"
          >
            關閉
          </button>
        </div>
        <div className="flex-1 min-h-0">{pane()}</div>
      </div>
    </div>
  );
}

export default FileOpener;
