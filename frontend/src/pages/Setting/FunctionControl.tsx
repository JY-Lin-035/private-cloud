import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { PowerOff, Power } from "lucide-react";
import { adminApi, type FeatureFlagInfo } from "../../api/adminApi";
import { authApi } from "../../api/authApi";

interface Props {
  layoutClass?: string;
}

const FLAG_LABELS: Record<string, string> = {
  allow_registration: "開放註冊",
  enable_verification_email: "註冊驗證信",
  enable_auth_code_email: "驗證碼郵件",
};

const FLAG_HINTS: Record<string, string> = {
  allow_registration: "關閉後登入頁將隱藏註冊入口，後端同時拒絕註冊請求。",
  enable_verification_email: "關閉時新帳號無法完成信箱驗證流程，註冊功能將一併暫停。",
  enable_auth_code_email: "關閉後密碼重設與信箱變更的驗證碼郵件將暫停發送。",
};

function FunctionControl({ layoutClass = "" }: Props) {
  const nav = useNavigate();
  const [loading, setLoading] = useState(true);
  const [adminUser, setAdminUser] = useState(false);
  const [flags, setFlags] = useState<FeatureFlagInfo[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null);

  useEffect(() => {
    authApi.checkSession().then((s: any) => {
      if (s.authenticated && s.identity === 1) {
        setAdminUser(true);
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
    if (adminUser) loadFlags();
  }, [adminUser, loadFlags]);

  async function toggle(flag: FeatureFlagInfo) {
    if (busyKey === flag.key) return;
    setBusyKey(flag.key);
    setNotice(null);
    try {
      const updated = await adminApi.updateFeatureFlag(flag.key, !flag.enabled);
      setFlags(prev => prev.map(f => f.key === updated.key ? { ...f, enabled: updated.enabled } : f));
      setNotice({ text: `「${FLAG_LABELS[flag.key] ?? flag.key}」已${updated.enabled ? "開啟" : "關閉"}`, ok: true });
    } catch (e: any) {
      setNotice({ text: e?.message ?? "更新失敗，請稍後再試", ok: false });
    }
    setBusyKey(null);
  }

  if (loading || !adminUser) return null;

  return (
    <div className={`flex flex-col min-h-screen text-white p-4 sm:p-6 ${layoutClass}`}>
      <div className="w-full max-w-7xl mx-auto mt-[1%] flex-1">
        <div className="mb-4 flex flex-col sm:flex-row justify-between items-center gap-2">
          <h2 className="text-xl font-semibold text-cyan-400 uppercase tracking-wider">Function Control</h2>
          {notice && (
            <span className={`px-3 py-1 rounded-full text-xs font-medium ring-1 ${notice.ok ? "bg-green-900/30 text-green-400 ring-green-500/30" : "bg-red-900/30 text-red-400 ring-red-500/30"}`}>
              {notice.text}
            </span>
          )}
        </div>

        {/* Mobile cards — visible on < sm */}
        <div className="block sm:hidden space-y-4">
          {flags.map(flag => (
            <div key={flag.key} className="bg-gray-800/50 rounded-lg border border-gray-700 p-4 space-y-3">
              <div className="flex justify-between items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-cyan-400 truncate">{FLAG_LABELS[flag.key] ?? flag.key}</div>
                  <div className="text-xs text-gray-400">{FLAG_HINTS[flag.key] ?? flag.description}</div>
                </div>
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ring-1 ${flag.enabled ? "bg-green-900/30 text-green-400 ring-green-500/30" : "bg-red-900/30 text-red-400 ring-red-500/30"}`}>
                  {flag.enabled ? "Enabled" : "Disabled"}
                </span>
              </div>
              <button
                onClick={() => toggle(flag)}
                disabled={busyKey === flag.key}
                className={`cursor-pointer w-full flex items-center justify-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded transition-colors text-white disabled:opacity-50 disabled:cursor-not-allowed
                  ${flag.enabled ? "bg-red-600 hover:bg-red-700" : "bg-green-600 hover:bg-green-700"}`}
              >
                {flag.enabled ? <PowerOff className="w-3.5 h-3.5" /> : <Power className="w-3.5 h-3.5" />}
                {flag.enabled ? "Disable" : "Enable"}
              </button>
            </div>
          ))}
        </div>

        {/* Desktop table — sm and up */}
        <div className="hidden sm:flex sm:justify-center w-full">
          <div className="w-full max-w-[90vw] rounded-lg border border-gray-700 bg-gray-800/50 overflow-x-auto scrollbar-hide">
            <table className="w-full table-fixed text-center">
              <thead>
                <tr>
                  <th className="text-center px-6 py-3 text-base font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[22%]">Function</th>
                  <th className="text-center px-6 py-3 text-base font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[48%]">Description</th>
                  <th className="text-center px-6 py-3 text-base font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[15%]">Status</th>
                  <th className="text-center px-6 py-3 text-base font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[15%]">Actions</th>
                </tr>
              </thead>
              <tbody>
                {flags.map(flag => (
                  <tr key={flag.key} className="hover:bg-gray-800/50 transition-colors border-b border-gray-700/50">
                    <td className="px-6 py-4 text-sm font-medium text-cyan-400 truncate">{FLAG_LABELS[flag.key] ?? flag.key}</td>
                    <td className="px-6 py-4 text-sm text-gray-300">{FLAG_HINTS[flag.key] ?? flag.description}</td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ring-1 ${flag.enabled ? "bg-green-900/30 text-green-400 ring-green-500/30" : "bg-red-900/30 text-red-400 ring-red-500/30"}`}>
                        {flag.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <button
                        onClick={() => toggle(flag)}
                        disabled={busyKey === flag.key}
                        className={`cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded transition-colors text-white disabled:opacity-50 disabled:cursor-not-allowed
                          ${flag.enabled ? "bg-red-600 hover:bg-red-700" : "bg-green-600 hover:bg-green-700"}`}
                      >
                        {flag.enabled ? <PowerOff className="w-3.5 h-3.5" /> : <Power className="w-3.5 h-3.5" />}
                        {flag.enabled ? "Disable" : "Enable"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <p className="mt-4 text-xs text-gray-500">變更即時寫入資料庫並生效，操作會記錄於伺服器日誌。</p>
      </div>
    </div>
  );
}

export default FunctionControl;
