import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pencil, Ban, ShieldCheck } from "lucide-react";
import { ipControlApi, type ControlRule } from "../../api/ipControlApi";
import { authApi } from "../../api/authApi";

interface Props { layoutClass?: string }

const fmt = (iso: string | null) => iso
  ? new Date(iso.endsWith('Z') ? iso : iso + 'Z').toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '';

function subjectLabel(r: ControlRule): string {
  if (r.subject_type === 'user') return `帳號 ${r.username ?? '?'}`;
  if (r.subject_type === 'ip_token') return `${r.ip_masked} → 連結 #${r.token_prefix}`;
  return r.ip_masked ?? '-';
}

function IPManagement({ layoutClass = "" }: Props) {
  const nav = useNavigate();
  const [loading, setLoading] = useState(true);
  const [adminUser, setAdminUser] = useState(false);
  const [tab, setTab] = useState<'ip' | 'user'>('ip');
  const [rules, setRules] = useState<ControlRule[]>([]);
  const [scores, setScores] = useState<{ masked: string; score: number | string }[]>([]);
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const [fType, setFType] = useState<'ip' | 'ip_token' | 'user'>('ip');
  const [fIp, setFIp] = useState('');
  const [fToken, setFToken] = useState('');
  const [fUser, setFUser] = useState('');
  const [fAction, setFAction] = useState<'slow' | 'block'>('slow');
  const [fScope, setFScope] = useState<'transfer' | 'full'>('transfer');
  const [fDir, setFDir] = useState<'up' | 'down' | 'both'>('both');
  const [fDelay, setFDelay] = useState('2000');
  const [fUpK, setFUpK] = useState('256');
  const [fDnK, setFDnK] = useState('512');
  const [fHours, setFHours] = useState('1');
  const [fReason, setFReason] = useState('');

  const [editId, setEditId] = useState<number | null>(null);
  const [eAction, setEAction] = useState<'slow' | 'block'>('slow');
  const [eScope, setEScope] = useState<'transfer' | 'full'>('transfer');
  const [eDir, setEDir] = useState<'up' | 'down' | 'both'>('both');
  const [eDelay, setEDelay] = useState('');
  const [eUpK, setEUpK] = useState('');
  const [eDnK, setEDnK] = useState('');
  const [eHours, setEHours] = useState('1');
  const [eReason, setEReason] = useState('');

  useEffect(() => {
    authApi.checkSession().then((s: any) => {
      if (s.authenticated && s.identity === 1) { setAdminUser(true); setLoading(false); }
      else nav("/login");
    });
  }, [nav]);

  const load = useCallback(async () => {
    try {
      const d = await ipControlApi.list();
      setRules(d.rules);
      setScores(d.top_scores || []);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { if (adminUser) load(); }, [adminUser, load]);

  async function run(fn: () => Promise<void>, okMsg: string) {
    if (busy) return;
    setBusy(true); setNotice(null);
    try { await fn(); setNotice({ text: okMsg, ok: true }); await load(); }
    catch (e: any) { setNotice({ text: e?.message ?? '操作失敗', ok: false }); }
    setBusy(false);
  }

  function create() {
    run(async () => {
      await ipControlApi.create({
        subject_type: fType,
        ip: fType === 'user' ? null : fIp.trim() || null,
        token: fType === 'ip_token' ? fToken.trim() : null,
        username: fType === 'user' ? fUser.trim() : null,
        action: fAction, scope: fScope, direction: fDir,
        delay_ms: Number(fDelay) || 0,
        upload_kbps: (fDir !== 'down' && fUpK) ? Number(fUpK) : null,
        download_kbps: (fDir !== 'up' && fDnK) ? Number(fDnK) : null,
        expires_in_hours: fHours ? Number(fHours) : null,
        reason: fReason.trim() || '手動設定',
      });
      setFIp(''); setFToken(''); setFUser(''); setFReason('');
    }, '管控已新增');
  }

  function startEdit(r: ControlRule) {
    setEditId(r.id);
    setEAction(r.action); setEScope(r.scope); setEDir(r.direction);
    setEDelay(String(r.delay_ms ?? 0));
    setEUpK(r.upload_kbps ? String(r.upload_kbps) : '');
    setEDnK(r.download_kbps ? String(r.download_kbps) : '');
    setEHours('1'); setEReason(r.reason ?? '');
  }

  function saveEdit() {
    if (editId == null) return;
    run(async () => {
      await ipControlApi.update(editId, {
        action: eAction, scope: eScope, direction: eDir,
        delay_ms: Number(eDelay) || 0,
        upload_kbps: (eDir !== 'down' && eUpK) ? Number(eUpK) : null,
        download_kbps: (eDir !== 'up' && eDnK) ? Number(eDnK) : null,
        expires_in_hours: eHours ? Number(eHours) : null,
        reason: eReason.trim() || undefined,
      });
      setEditId(null);
    }, '管控已更新');
  }

  const escalate = (r: ControlRule) =>
    run(() => ipControlApi.update(r.id, { action: 'block', scope: 'full' }).then(() => undefined), '已升級為全站 429');

  const release = (r: ControlRule) => {
    if (!window.confirm(`確定解除 ${subjectLabel(r)} 的管控？`)) return Promise.resolve();
    return run(() => ipControlApi.remove(r.id).then(() => undefined), '已解除管控');
  };

  const suspend = (username: string) => {
    if (!window.confirm(`確定要將帳號「${username}」關入小黑屋並踢出登入？`)) return;
    run(() => ipControlApi.suspendAccount(username).then(() => undefined), `帳號 ${username} 已停用`);
  };

  if (loading || !adminUser) return null;

  const shown = rules.filter(r => (tab === 'ip' ? r.subject_type !== 'user' : r.subject_type === 'user'));

  const cell = "px-3 py-2 text-sm align-top";
  const inputCls = "bg-gray-700 text-white px-2 py-1.5 rounded border border-gray-600 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500";

  return (
    <div className={`flex flex-col min-h-screen text-white p-4 sm:p-6 ${layoutClass}`}>
      <div className="w-full max-w-7xl mx-auto mt-[1%] flex-1">
        <div className="mb-4 flex flex-col sm:flex-row justify-between items-center gap-2">
          <h2 className="text-xl font-semibold text-cyan-400 uppercase tracking-wider">IP Management</h2>
          {notice && (
            <span className={`px-3 py-1 rounded-full text-xs font-medium ring-1 ${notice.ok ? "bg-green-900/30 text-green-400 ring-green-500/30" : "bg-red-900/30 text-red-400 ring-red-500/30"}`}>
              {notice.text}
            </span>
          )}
        </div>

        {tab === 'ip' && scores.length > 0 && (
          <div className="mb-4 bg-gray-800/50 rounded-lg border border-gray-700 p-3">
            <p className="text-xs text-gray-400 mb-2 uppercase tracking-wider">積分儀表板（近 1 小時）</p>
            <div className="flex flex-wrap gap-2">
              {scores.map((s, i) => (
                <span key={i} className="px-2 py-1 rounded text-xs bg-gray-700 text-gray-200">
                  {s.masked}：<span className={s.score ? 'text-red-400 font-semibold' : 'text-gray-400'}>{String(s.score)}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* create form */}
        <div className="mb-4 bg-gray-800/50 rounded-lg border border-gray-700 p-3 grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
          <select value={fType} onChange={e => setFType(e.target.value as any)} className={inputCls}>
            <option value="ip">對象：全站 IP</option>
            <option value="ip_token">對象：IP×連結</option>
            <option value="user">對象：帳號</option>
          </select>
          {fType !== 'user' ? (
            <input placeholder="IP（例 1.2.3.4）" value={fIp} onChange={e => setFIp(e.target.value)} className={inputCls} />
          ) : (
            <input placeholder="帳號名稱" value={fUser} onChange={e => setFUser(e.target.value)} className={inputCls} />
          )}
          {fType === 'ip_token' && (
            <input placeholder="連結 token" value={fToken} onChange={e => setFToken(e.target.value)} className={inputCls} />
          )}
          <select value={fAction} onChange={e => setFAction(e.target.value as any)} className={inputCls}>
            <option value="slow">動作：慢速</option>
            <option value="block">動作：429 封鎖</option>
          </select>
          <select value={fScope} onChange={e => setFScope(e.target.value as any)} className={inputCls}>
            <option value="transfer">範圍：僅傳輸</option>
            <option value="full">範圍：全站</option>
          </select>
          <select value={fDir} onChange={e => setFDir(e.target.value as any)} className={inputCls}>
            <option value="both">方向：上+下</option>
            <option value="up">方向：上傳</option>
            <option value="down">方向：下載</option>
          </select>
          <input placeholder="延遲 ms" type="number" min="0" value={fDelay} onChange={e => setFDelay(e.target.value)} className={inputCls} />
          <div className="flex gap-2">
            <input placeholder="上傳KB/s" type="number" min="16" value={fUpK} onChange={e => setFUpK(e.target.value)} className={inputCls + ' flex-1 min-w-0'} />
            <input placeholder="下載KB/s" type="number" min="16" value={fDnK} onChange={e => setFDnK(e.target.value)} className={inputCls + ' flex-1 min-w-0'} />
          </div>
          <select value={fHours} onChange={e => setFHours(e.target.value)} className={inputCls}>
            <option value="1">期限：1 小時</option>
            <option value="6">期限：6 小時</option>
            <option value="24">期限：24 小時</option>
            <option value="">無限期</option>
          </select>
          <input placeholder="原因" value={fReason} onChange={e => setFReason(e.target.value)} className={inputCls} />
          <button onClick={create} disabled={busy}
            className="cursor-pointer px-4 py-1.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors">
            新增管控
          </button>
        </div>

        {/* tabs */}
        <div className="mb-2 flex gap-2">
          <button onClick={() => setTab('ip')} className={`px-4 py-1.5 rounded-t text-sm cursor-pointer ${tab === 'ip' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}>IP 管控</button>
          <button onClick={() => setTab('user')} className={`px-4 py-1.5 rounded-t text-sm cursor-pointer ${tab === 'user' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}>帳號管控</button>
        </div>

        <div className="w-full rounded-lg border border-gray-700 bg-gray-800/50 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th className="px-3 py-3 text-xs font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[6%]">序號</th>
                <th className="px-3 py-3 text-xs font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[20%]">對象</th>
                <th className="px-3 py-3 text-xs font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[22%]">處置</th>
                <th className="px-3 py-3 text-xs font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[16%]">到期</th>
                <th className="px-3 py-3 text-xs font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[18%]">近期帳號</th>
                <th className="px-3 py-3 text-xs font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 text-center">操作</th>
              </tr>
            </thead>
            <tbody>
              {shown.map(r => (
                <tr key={r.id} className="border-b border-gray-700/50 hover:bg-gray-800/50 align-top">
                  <td className={cell + ' text-gray-400'}>#{r.id}</td>
                  <td className={cell}>
                    <div className="break-all">{subjectLabel(r)}</div>
                    <div className="text-xs text-gray-500 mt-1">{r.reason}{r.auto ? '（自動）' : ''}</div>
                  </td>
                  <td className={cell}>
                    {editId === r.id ? (
                      <div className="flex flex-col gap-2">
                        <div className="flex gap-2">
                          <select value={eAction} onChange={e => setEAction(e.target.value as any)} className={inputCls}>
                            <option value="slow">慢速</option>
                            <option value="block">429</option>
                          </select>
                          <select value={eScope} onChange={e => setEScope(e.target.value as any)} className={inputCls}>
                            <option value="transfer">傳輸</option>
                            <option value="full">全站</option>
                          </select>
                          <select value={eDir} onChange={e => setEDir(e.target.value as any)} className={inputCls}>
                            <option value="both">上下</option>
                            <option value="up">上</option>
                            <option value="down">下</option>
                          </select>
                        </div>
                        <div className="flex gap-2 flex-wrap">
                          <input value={eDelay} onChange={e => setEDelay(e.target.value)} placeholder="延遲ms" type="number" className={inputCls + ' w-24'} />
                          <input value={eUpK} onChange={e => setEUpK(e.target.value)} placeholder="上KB/s" type="number" className={inputCls + ' w-24'} />
                          <input value={eDnK} onChange={e => setEDnK(e.target.value)} placeholder="下KB/s" type="number" className={inputCls + ' w-24'} />
                          <select value={eHours} onChange={e => setEHours(e.target.value)} className={inputCls}>
                            <option value="1">1h</option><option value="6">6h</option><option value="24">24h</option><option value="">∞</option>
                          </select>
                        </div>
                        <input value={eReason} onChange={e => setEReason(e.target.value)} placeholder="原因" className={inputCls} />
                        <span className="flex gap-2">
                          <button onClick={saveEdit} className="cursor-pointer px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-xs rounded">儲存</button>
                          <button onClick={() => setEditId(null)} className="cursor-pointer px-3 py-1 bg-red-600 hover:bg-red-700 text-white text-xs rounded">取消</button>
                        </span>
                      </div>
                    ) : (
                      <span className="flex flex-col gap-1">
                        <span className={`inline-flex w-max items-center px-2 py-0.5 rounded-full text-xs font-medium ring-1 ${r.action === 'block' ? 'bg-red-900/30 text-red-400 ring-red-500/30' : 'bg-amber-900/30 text-amber-300 ring-amber-500/30'}`}>
                          {r.action === 'block' ? '429 封鎖' : '慢速'}・{r.scope === 'full' ? '全站' : '傳輸'}・{r.direction === 'both' ? '上下' : r.direction === 'up' ? '上' : '下'}
                        </span>
                        {r.action === 'slow' && (
                          <span className="text-xs text-gray-400">
                            {r.delay_ms ? `${r.delay_ms}ms/請求` : ''}{r.upload_kbps ? `　↑${r.upload_kbps}KB/s` : ''}{r.download_kbps ? `　↓${r.download_kbps}KB/s` : ''}
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  <td className={cell + ' text-sm'}>{r.expires_at ? fmt(r.expires_at) : <span className="text-gray-500">無限期</span>}</td>
                  <td className={cell}>
                    {r.recent_accounts.length === 0 ? <span className="text-xs text-gray-500">匿名（無帳號）</span> : (
                      <div className="flex flex-col gap-1">
                        {r.recent_accounts.map(u => (
                          <span key={u} className="flex items-center gap-2 text-sm">
                            {u}
                            <button onClick={() => suspend(u)} className="text-xs px-2 py-0.5 rounded bg-red-700 hover:bg-red-600 cursor-pointer whitespace-nowrap">停用</button>
                          </span>
                        ))}
                      </div>
                    )}
                  </td>
                  <td className={cell + ' text-center'}>
                    <span className="flex items-center justify-center gap-3">
                      <Pencil className="w-5 h-5 text-cyan-300 cursor-pointer" onClick={() => startEdit(r)} />
                      {r.action !== 'block' && <Ban className="w-5 h-5 text-red-400 cursor-pointer" onClick={() => escalate(r)} />}
                      <ShieldCheck className="w-5 h-5 text-green-400 cursor-pointer" onClick={() => release(r)} />
                    </span>
                  </td>
                </tr>
              ))}
              {shown.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-500 text-sm">目前沒有管控對象。異常來源會由系統自動加入慢速管控，也可手動新增。</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-xs text-gray-500">
          處置台階：傳輸慢速 → 全站限速 → 全站 429 → 停用帳號。所有完整 IP 與明細僅記錄於伺服器 security.log，介面上一律中段遮罩顯示。
        </p>
      </div>
    </div>
  );
}

export default IPManagement;
