import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { adminApi, type FeatureFlagInfo } from "../../api/adminApi";
import { authApi } from "../../api/authApi";

interface Props {
  layoutClass?: string;
}

const FLAG_LABELS: Record<string, string> = {
  allow_registration: "開放註冊",
  enable_verification_email: "註冊驗證信",
  enable_auth_code_email: "驗證碼郵件（密碼重設／信箱變更）",
};

function FunctionControl({ layoutClass = "" }: Props) {
  const nav = useNavigate();
  const [loading, setLoading] = useState(true);
  const [flags, setFlags] = useState<FeatureFlagInfo[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [notice, setNotice] = useState('');

  useEffect(() => {
    authApi.checkSession().then((s: any) => {
      if (s.authenticated && s.identity === 1) {
        setLoading(false);
      } else {
        nav("/login");
      }
    });
  }, [nav]);

  const loadFlags = useCallback(async () => {
    try {
      setFlags(await adminApi.getFeatureFlags());
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    if (!loading) loadFlags();
  }, [loading, loadFlags]);

  async function toggle(flag: FeatureFlagInfo) {
    setBusyKey(flag.key);
    setNotice('');
    try {
      const updated = await adminApi.updateFeatureFlag(flag.key, !flag.enabled);
      setFlags(prev => prev.map(f => f.key === updated.key ? { ...f, enabled: updated.enabled } : f));
      setNotice(`「${FLAG_LABELS[flag.key] ?? flag.key}」已${updated.enabled ? '開啟' : '關閉'}`);
    } catch (e: any) {
      setNotice(e?.message ?? '更新失敗，請稍後再試');
    }
    setBusyKey(null);
  }

  if (loading) {
    return <div className={`flex items-center justify-center ${layoutClass}`}><p className="text-gray-500">載入中…</p></div>;
  }

  return (
    <div className={`bg-white rounded-xl shadow-md p-6 w-[92vw] max-w-2xl mx-auto ${layoutClass}`}>
      <h2 className="text-xl font-bold mb-1">Function Control</h2>
      <p className="text-sm text-gray-500 mb-4">控制各功能的啟用狀態，變更立即生效並寫入資料庫。</p>
      {notice && (
        <p className="mb-3 text-sm px-3 py-2 rounded bg-blue-50 text-blue-700">{notice}</p>
      )}
      <ul className="divide-y">
        {flags.map(flag => (
          <li key={flag.key} className="flex items-center justify-between py-4 gap-4">
            <div>
              <p className="font-medium">{FLAG_LABELS[flag.key] ?? flag.key}</p>
              <p className="text-sm text-gray-400">{flag.description}</p>
            </div>
            <button
              onClick={() => toggle(flag)}
              disabled={busyKey === flag.key}
              className={`relative w-12 h-6 rounded-full transition-colors shrink-0 ${flag.enabled ? 'bg-green-500' : 'bg-gray-300'} ${busyKey === flag.key ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
              aria-label={`${FLAG_LABELS[flag.key] ?? flag.key} 開關`}
            >
              <span className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow transition-transform ${flag.enabled ? 'translate-x-6' : ''}`} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default FunctionControl;
