import { API_BASE_URL } from '../../config/api';
import { useEffect, useRef, useState } from 'react';
import { classify, extOf } from '../../utils/fileClass';
import { mediaSrc, swControlsDocument, onMediaCacheEvent, purgeMediaCache } from '../../utils/mediaCache';

interface Props {
  uuid: string;
  filename: string;
  updatedAt: string;
}

/** Media/image/pdf inline player backed by the /__media service worker cache. */
function MediaPane({ uuid, filename, updatedAt }: Props) {
  const cat = classify(filename);

  const [cacheState, setCacheState] = useState<'idle' | 'warming' | 'cached' | 'skip'>('idle');
  const [skipReason, setSkipReason] = useState('');
  const [unsupported, setUnsupported] = useState(false);
  const [swReady, setSwReady] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void swControlsDocument().then((ok) => { setUnsupported(!ok); setSwReady(true); });
    const off = onMediaCacheEvent((ev) => {
      if (ev.uuid !== uuid) return;
      if (ev.type === 'media-cached') setCacheState('cached');
      else if (ev.type === 'media-skip') { setCacheState('skip'); setSkipReason(ev.reason || ''); }
    });
    return () => {
      off();
      // player closed: pause background caching for this file (partial kept for resume)
      try {
        void navigator.serviceWorker?.ready.then((r) => r.active?.postMessage({ type: 'media-stop', uuid })).catch(() => { /* noop */ });
      } catch { /* noop */ }
    };
  }, [uuid]);

  const MIME: Record<string, string> = { mp4: 'video/mp4', webm: 'video/webm', mov: 'video/quicktime',
    m4v: 'video/mp4', ogv: 'video/ogg', mp3: 'audio/mpeg', wav: 'audio/wav', ogg: 'audio/ogg',
    m4a: 'audio/mp4', aac: 'audio/aac', flac: 'audio/flac', opus: 'audio/ogg',
    png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif',
    webp: 'image/webp', bmp: 'image/bmp', avif: 'image/avif', ico: 'image/x-icon', pdf: 'application/pdf' };
  const mime = MIME[extOf(filename)] || 'application/octet-stream';
  const [src, setSrc] = useState<string>('');
  useEffect(() => {
    if (unsupported) { setSrc(`${API_BASE_URL}/api/files/stream?uuid=${encodeURIComponent(uuid)}`); }
    else { void mediaSrc(uuid, updatedAt, mime).then((s) => { setCacheState((c) => (c === 'idle' ? 'warming' : c)); setSrc(s); }); }
  }, [unsupported, uuid, updatedAt, mime]);
  if (!swReady) return <div className="h-full flex items-center justify-center text-gray-400">初始化媒體快取…</div>;

  return (
    <div ref={ref} className="h-full flex flex-col bg-black">
      <div className="flex items-center gap-3 px-3 py-1.5 bg-gray-800 text-gray-200 text-xs shrink-0">
        <span className="truncate max-w-[60%]" title={filename}>{filename}</span>
        <div className="flex-1" />
        {!unsupported && cat === 'video' && (
          cacheState === 'cached' ? <span className="text-green-400">✓ 已存本地快取</span>
          : cacheState === 'skip' ? <span className="text-amber-400" title={skipReason}>{skipReason || '僅串流播放'}</span>
          : cacheState === 'warming' ? <span className="text-gray-400">背景快取中…{skipReason ? `(${skipReason})` : ''}</span>
          : <span className="text-gray-400">載入中…</span>
        )}
        {!unsupported && cat === 'video' && (
          <button type="button" className="px-2 py-0.5 rounded bg-gray-700 hover:bg-gray-600"
            onClick={() => purgeMediaCache()}>清除媒體快取</button>
        )}
      </div>
      <div className="flex-1 min-h-0 flex items-center justify-center">
        {cat === 'video' && (
          <video controls preload="metadata" src={src} className="w-full h-full object-contain" />
        )}
        {cat === 'audio' && (
          <audio controls src={src} className="w-full max-w-2xl px-6" />
        )}
        {cat === 'image' && (
          <img src={src} alt={filename} className="w-full h-full object-contain" />
        )}

      </div>
    </div>
  );
}

export default MediaPane;
