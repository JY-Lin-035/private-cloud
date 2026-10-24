import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Download } from 'lucide-react';
import { API_BASE_URL } from '../../config/api';
import { shareApi } from '../../api/shareApi';


type SharePageState = 'checking' | 'ready' | 'password' | 'notfound' | 'expired';

function DownloadShareFile({ layoutClass = "" }: { layoutClass?: string }) {
  const { link } = useParams();
  const [pageState, setPageState] = useState<SharePageState>('checking');
  const [password, setPassword] = useState('');
  const [ticket, setTicket] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const startDownload = (tk?: string | null) => {
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
        if (!st.password_required) {
          setPageState('ready');
          startDownload();
          return;
        }
        const cached = sessionStorage.getItem(`shareTicket:${link}`);
        if (cached) {
          setTicket(cached);
          setPageState('ready');
          startDownload(cached);
          return;
        }
        setPageState('password');
      } catch (e) {
        console.error(e);
        if (!cancelled) setPageState('ready');
      }
    })();
    return () => { cancelled = true; };
  }, [link]);

  async function submitPassword() {
    if (!link || !password || busy) return;
    setBusy(true);
    setError('');
    try {
      const r = await shareApi.verifyPassword(link, password);
      sessionStorage.setItem(`shareTicket:${link}`, r.ticket);
      setTicket(r.ticket);
      setPageState('ready');
      startDownload(r.ticket);
    } catch (e: any) {
      setError(e?.message ?? '驗證失敗，請稍後再試');
    }
    setBusy(false);
  }

  if (pageState === 'checking') {
    return (
      <div className={`flex flex-col justify-center items-center bg-gray-300 ${layoutClass}`}>
        <h1 className="text-2xl md:text-4xl text-blue-400 font-extrabold">載入中…</h1>
      </div>
    );
  }

  if (pageState === 'notfound' || pageState === 'expired') {
    return (
      <div className={`flex flex-col justify-center items-center bg-gray-300 ${layoutClass}`}>
        <h1 className="text-2xl sm:text-3xl md:text-4xl text-red-400 font-extrabold tracking-tight text-center px-4">
          {pageState === 'notfound' ? '分享連結不存在或已被移除' : '分享連結已過期'}
        </h1>
      </div>
    );
  }

  if (pageState === 'password') {
    return (
      <div className={`flex flex-col justify-center items-center bg-gray-300 ${layoutClass}`}>
        <div className="w-[90vw] max-w-[400px] bg-white rounded-xl shadow-md p-6 flex flex-col items-center gap-4">
          <span className="text-3xl">🔒</span>
          <h2 className="text-xl font-bold text-gray-800">此分享受密碼保護</h2>
          <p className="text-sm text-gray-500 text-center">請向分享者取得密碼後下載檔案</p>
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
            {busy ? '驗證中…' : '解鎖並下載'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex flex-col justify-center items-center bg-gray-300 ${layoutClass}`}>
      <h1 className="text-xl sm:text-2xl md:text-4xl lg:text-5xl xl:text-[5rem] text-blue-400 font-extrabold tracking-tight leading-none text-center px-4">
        若未開始下載請點擊下方按鈕
      </h1>

      <div
        className="mt-[5vh] flex justify-center items-center bg-green-100 rounded-[3rem] sm:rounded-[6rem] p-4 sm:p-6 cursor-pointer"
        onClick={() => startDownload(ticket)}
      >
        <Download className="w-[5vh] sm:w-[8vh] md:w-[10vh] h-[5vh] sm:h-[8vh] md:h-[10vh] mr-2 text-green-600 inline-block align-middle" />
        <span className="text-xl sm:text-2xl md:text-[3.2rem] align-middle text-green-600">開始下載</span>
      </div>
    </div>
  );
}

export default DownloadShareFile;
