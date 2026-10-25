import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Download, FolderOpen, FileText, ChevronLeft } from 'lucide-react';
import { API_BASE_URL } from '../../config/api';
import { shareApi } from '../../api/shareApi';


type PageState = 'checking' | 'ready' | 'password' | 'notfound' | 'expired' | 'folder';

interface Listing {
  name: string;
  folders: { name: string; size: number }[];
  files: { name: string; size: number }[];
}

function formatSize(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let v = bytes;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v < 10 && i > 0 ? v.toFixed(1) : Math.round(v)} ${units[i]}`;
}

function DownloadShareFile({ layoutClass = "" }: { layoutClass?: string }) {
  const { link } = useParams();
  const [pageState, setPageState] = useState<PageState>('checking');
  const [password, setPassword] = useState('');
  const [ticket, setTicket] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  // folder browse state
  const [sub, setSub] = useState('');
  const [listing, setListing] = useState<Listing | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const rootNameRef = useRef<string | null>(null);

  const startFileDownload = (tk?: string | null) => {
    const url = `${API_BASE_URL}/api/share/downloadFile?link=${link}&t=${Date.now()}${tk ? `&ticket=${encodeURIComponent(tk)}` : ''}`;
    const tempLink = document.createElement("a");
    tempLink.href = url;
    tempLink.download = "UnKnown";
    document.body.appendChild(tempLink);
    tempLink.click();
    document.body.removeChild(tempLink);
  };

  useEffect(() => {
    if (!link) return;
    let cancelled = false;
    (async () => {
      try {
        const st = await shareApi.status(link);
        if (cancelled) return;
        if (!st.exists) { setPageState('notfound'); return; }
        if (st.expired) { setPageState('expired'); return; }
        const cached = sessionStorage.getItem(`shareTicket:${link}`);
        const tk = st.password_required ? (cached || null) : null;
        if (st.password_required && !cached) { setPageState('password'); return; }
        setTicket(tk);
        if (st.type === 'folder') {
          setPageState('folder');
        } else {
          setPageState('ready');
          startFileDownload(tk);
        }
      } catch (e) {
        console.error(e);
        if (!cancelled) setPageState('ready');
      }
    })();
    return () => { cancelled = true; };
  }, [link]);

  const loadListing = useCallback(async () => {
    if (!link || pageState !== 'folder') return;
    try {
      const r = await shareApi.browseFolder(link, sub, ticket);
      if (!sub) rootNameRef.current = r.name;
      setListing(r);
      setSelected([]);
    } catch (e: any) {
      const msg = e?.message ?? '';
      if (/密碼/.test(msg)) { setPageState('password'); return; }
      setError(msg || '載入目錄失敗');
    }
  }, [link, sub, ticket, pageState]);

  useEffect(() => { loadListing(); }, [loadListing]);

  async function submitPassword() {
    if (!link || !password || busy) return;
    setBusy(true);
    setError('');
    try {
      const r = await shareApi.verifyPassword(link, password);
      sessionStorage.setItem(`shareTicket:${link}`, r.ticket);
      setTicket(r.ticket);
      const st = await shareApi.status(link);
      if (st.type === 'folder') {
        setPageState('folder');
      } else {
        setPageState('ready');
        startFileDownload(r.ticket);
      }
    } catch (e: any) {
      setError(e?.message ?? '驗證失敗，請稍後再試');
    }
    setBusy(false);
  }

  function togglePath(p: string) {
    setSelected(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);
  }

  function joinPath(base: string, name: string) {
    return base ? `${base}/${name}` : name;
  }

  const shell = (inner: React.ReactNode) => (
    <div className={`flex flex-col justify-center items-center bg-gray-300 ${layoutClass}`}>
      {inner}
    </div>
  );

  if (pageState === 'checking') {
    return shell(<h1 className="text-2xl md:text-4xl text-blue-400 font-extrabold">載入中…</h1>);
  }

  if (pageState === 'notfound' || pageState === 'expired') {
    return shell(
      <h1 className="text-2xl sm:text-3xl md:text-4xl text-red-400 font-extrabold tracking-tight text-center px-4">
        {pageState === 'notfound' ? '分享連結不存在或已被移除' : '分享連結已過期'}
      </h1>
    );
  }

  if (pageState === 'password') {
    return shell(
      <div className="w-[90vw] max-w-[400px] bg-white rounded-xl shadow-md p-6 flex flex-col items-center gap-4">
        <span className="text-3xl">🔒</span>
        <h2 className="text-xl font-bold text-gray-800">此分享受密碼保護</h2>
        <p className="text-sm text-gray-500 text-center">請向分享者取得密碼後繼續</p>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') submitPassword(); }}
          placeholder="請輸入密碼"
          autoComplete="off"
          className="w-full px-3 py-2 border rounded text-gray-900"
        />
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="button"
          onClick={submitPassword}
          disabled={!password || busy}
          className={`w-full px-4 py-2 text-white rounded ${!password || busy ? 'bg-gray-400' : 'bg-blue-500 hover:bg-blue-600 cursor-pointer'}`}
        >
          {busy ? '驗證中…' : '解鎖'}
        </button>
      </div>
    );
  }

  if (pageState === 'folder') {
    const segs = sub ? sub.split('/') : [];
    return shell(
      <div className="w-[94vw] max-w-[760px] bg-white rounded-xl shadow-md p-4 sm:p-6 text-gray-900">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <h2 className="text-lg font-bold truncate">📁 {listing?.name ?? '…'}</h2>
          <button
            onClick={async () => { try { await shareApi.downloadFolderZipPublic(link!, ticket, listing?.name ?? 'shared'); } catch (e: any) { setError(e?.message ?? '下載失敗'); } }}
            className="px-3 py-1.5 rounded bg-green-600 hover:bg-green-700 text-white text-sm cursor-pointer"
          >
            下載整個資料夾（ZIP）
          </button>
        </div>

        <div className="flex items-center gap-2 mt-3 mb-1 text-sm text-gray-600">
          {segs.length > 0 && (
            <button
              onClick={() => setSub(segs.slice(0, -1).join('/'))}
              className="inline-flex items-center text-blue-600 cursor-pointer"
            >
              <ChevronLeft className="w-4 h-4" /> 上一層
            </button>
          )}
          <span>{segs.length ? segs.join(' / ') : '（根目錄）'}</span>
        </div>
        {error && <p className="text-red-500 text-sm my-2">{error}</p>}

        <ul className="divide-y divide-gray-200 max-h-[52vh] overflow-y-auto border-y">
          {listing?.folders.map(f => {
            const p = joinPath(sub, f.name);
            return (
              <li key={`d:${p}`} className="flex items-center gap-3 py-2 px-1">
                {pageState === 'folder' && (
                  <input
                    type="checkbox"
                    checked={selected.includes(p)}
                    onChange={() => togglePath(p)}
                    className="w-4 h-4"
                  />
                )}
                <FolderOpen className="w-5 h-5 text-yellow-500 cursor-pointer" onClick={() => setSub(p)} />
                <button className="text-blue-700 hover:underline cursor-pointer flex-1 text-left truncate" onClick={() => setSub(p)}>{f.name}</button>
                <span className="text-xs text-gray-400">資料夾</span>
              </li>
            );
          })}
          {listing?.files.map(f => {
            const p = joinPath(sub, f.name);
            return (
              <li key={`f:${p}`} className="flex items-center gap-3 py-2 px-1">
                <input
                  type="checkbox"
                  checked={selected.includes(p)}
                  onChange={() => togglePath(p)}
                  className="w-4 h-4"
                />
                <FileText className="w-5 h-5 text-gray-400" />
                <span className="flex-1 truncate">{f.name}</span>
                <span className="text-xs text-gray-400">{formatSize(f.size)}</span>
              </li>
            );
          })}
          {listing && listing.folders.length === 0 && listing.files.length === 0 && (
            <li className="py-6 text-center text-gray-400 text-sm">這個資料夾是空的</li>
          )}
        </ul>

        <div className="mt-4 flex justify-between items-center">
          <span className="text-sm text-gray-500">已選 {selected.length} 項</span>
          <button
            onClick={async () => {
              if (!selected.length || busy) return;
              setBusy(true); setError('');
              try {
                await shareApi.downloadItemsPublic(link!, selected, ticket, rootNameRef.current);
              } catch (e: any) {
                setError(e?.message ?? '下載失敗');
              }
              setBusy(false);
            }}
            disabled={!selected.length || busy}
            className={`px-4 py-2 rounded text-white inline-flex items-center gap-2 ${!selected.length || busy ? 'bg-gray-400' : 'bg-blue-600 hover:bg-blue-700 cursor-pointer'}`}
          >
            <Download className="w-4 h-4" />
            {busy ? '準備中…' : '下載所選（ZIP）'}
          </button>
        </div>
      </div>
    );
  }

  return shell(
    <>
      <h1 className="text-xl sm:text-2xl md:text-4xl lg:text-5xl xl:text-[5rem] text-blue-400 font-extrabold tracking-tight leading-none text-center px-4">
        若未開始下載請點擊下方按鈕
      </h1>
      <div
        className="mt-[5vh] flex justify-center items-center bg-green-100 rounded-[3rem] sm:rounded-[6rem] p-4 sm:p-6 cursor-pointer"
        onClick={() => startFileDownload(ticket)}
      >
        <Download className="w-[5vh] sm:w-[8vh] md:w-[10vh] h-[5vh] sm:h-[8vh] md:h-[10vh] mr-2 text-green-600 inline-block align-middle" />
        <span className="text-xl sm:text-2xl md:text-[3.2rem] align-middle text-green-600">開始下載</span>
      </div>
    </>
  );
}

export default DownloadShareFile;
