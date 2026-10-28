import { useEffect, useRef, useState } from 'react';
import { API_BASE_URL } from '../../config/api';
import { classify } from '../../utils/fileClass';
import { mediaSrc, registerMediaSW, onMediaCacheEvent, purgeMediaCache } from '../../utils/mediaCache';

interface Props {
  uuid: string;
  filename: string;
  updatedAt: string;
  size: number;
}

/** Media/image/pdf inline player backed by the /__media service worker cache. */
function MediaPane({ uuid, filename, updatedAt, size }: Props) {
  const cat = classify(filename);
  const [cacheState, setCacheState] = useState<'idle' | 'warming' | 'cached' | 'skip'>('idle');
  const [unsupported, setUnsupported] = useState(false);
  const [swReady, setSwReady] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    registerMediaSW().then((ok) => { setUnsupported(!ok); setSwReady(true); });
    const off = onMediaCacheEvent((ev) => {
      if (ev.uuid !== uuid) return;
      if (ev.type === 'media-cached') setCacheState('cached');
      else if (ev.type === 'media-skip') setCacheState('skip');
    });
    return off;
  }, [uuid]);

  useEffect(() => {
    // re-purge when pane mounts for a session that may have changed account
    if (size > 0 && (cacheState === 'idle')) void 0;
  }, [size, cacheState]);

  const src = unsupported ? `${API_BASE_URL}/api/files/stream?uuid=${uuid}` : mediaSrc(uuid, updatedAt);
  if (!swReady) return <div className="h-full flex items-center justify-center text-gray-400">初始化媒體快取…</div>;

  return (
    <div ref={ref} className="h-full flex flex-col bg-black">
      <div className="flex items-center gap-3 px-3 py-1.5 bg-gray-800 text-gray-200 text-xs shrink-0">
        <span className="truncate max-w-[60%]" title={filename}>{filename}</span>
        <div className="flex-1" />
        {!unsupported && cat === 'video' && (
          cacheState === 'cached' ? <span className="text-green-400">✓ 已存本地快取</span>
          : cacheState === 'skip' ? <span className="text-amber-400">空間不足，僅串流</span>
          : <span className="text-gray-400">播放中背景快取…</span>
        )}
        {!unsupported && cat === 'video' && (
          <button type="button" className="px-2 py-0.5 rounded bg-gray-700 hover:bg-gray-600"
            onClick={() => purgeMediaCache()}>清除媒體快取</button>
        )}
      </div>
      <div className="flex-1 min-h-0 flex items-center justify-center">
        {cat === 'video' && (
          <video controls preload="metadata" src={src} className="max-h-full max-w-full" />
        )}
        {cat === 'audio' && (
          <audio controls src={src} className="w-full max-w-2xl px-6" />
        )}
        {cat === 'image' && (
          <img src={src} alt={filename} className="max-h-full max-w-full object-contain" />
        )}
        {cat === 'pdf' && (
          <iframe title={filename} src={src} className="w-full h-full bg-white" />
        )}
      </div>
    </div>
  );
}

export default MediaPane;
