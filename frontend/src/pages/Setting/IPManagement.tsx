import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pencil, Ban, ShieldCheck, X } from "lucide-react";
import { ipControlApi, type ControlRule } from "../../api/ipControlApi";
import { authApi } from "../../api/authApi";

interface Props { layoutClass?: string }

const fmt = (iso: string | null) => iso
  ? new Date(iso.endsWith('Z') ? iso : iso + 'Z').toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  : '';

function localToIso(v: string): string | null {
  if (!v) return null;
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return null;
  const off = -d.getTimezoneOffset();
  const sign = off >= 0 ? '+' : '-';
  const hh = String(Math.floor(Math.abs(off) / 60)).padStart(2, '0');
  const mm = String(Math.abs(off) % 60).padStart(2, '0');
  const base = v.length === 16 ? `${v}:00` : v;
  return `${base.slice(0, 19)}${sign}${hh}:${mm}`;
}

function subjectLabel(r: ControlRule): string {
  if (r.subject_type === 'user') return `帳號 ${r.username ?? '?'}`;
  if (r.subject_type === 'ip_token') return `${r.ip_masked} → 連結 #${r.token_prefix}`;
  return r.ip_masked ?? '-';
}

interface FormState {
  subject_type: 'ip' | 'ip_token' | 'user';
  ip: string;
  token: string;
  username: string;
  action: 'slow' | 'block';
  scope: 'transfer' | 'full';
  direction: 'up' | 'down' | 'both';
  delay: string;
  upK: string;
  dnK: string;
  hours: string;      // '1' | '6' | '24' | 'custom' | '' (indefinite)
  customAt: string;
  reason: string;
}

const emptyForm: FormState = {
  subject_type: 'ip', ip: '', token: '', username: '',
  action: 'slow', scope: 'transfer', direction: 'both',
  delay: '2000', upK: '256', dnK: '512',
  hours: '1', customAt: '', reason: '',
};

function toBody(f: FormState) {
  return {
    subject_type: f.subject_type,
    ip: f.subject_type === 'user' ? null : f.ip.trim() || null,
    token: f.subject_type === 'ip_token' ? f.token.trim() : null,
    username: f.subject_type === 'user' ? f.username.trim() : null,
    action: f.action,
    scope: f.scope,
    direction: f.scope === 'full' ? 'both' : f.direction,
    delay_ms: f.action === 'block' ? 0 : Number(f.delay) || 0,
    upload_kbps: (f.action !== 'block' && (f.scope === 'full' || f.direction !== 'down') && f.upK) ? Number(f.upK) : null,
    download_kbps: (f.action !== 'block' && (f.scope === 'full' || f.direction !== 'up') && f.dnK) ? Number(f.dnK) : null,
    expires_in_hours: (f.hours && f.hours !== 'custom') ? Number(f.hours) : null,
    expires_at: f.hours === 'custom' ? localToIso(f.customAt) : null,
    reason: f.reason.trim() || (f.action === 'block' ? '手動封鎖' : '手動設定'),
  };
}

function FormFields({ f, set, subjectFixed = false }: { f: FormState; set: (patch: Partial<FormState>) => void; subjectFixed?: boolean }) {
  const inputCls = "w-full bg-gray-700 text-white px-2 py-1.5 rounded border border-gray-600 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500 disabled:opacity-50";
  const labCls = "flex flex-col gap-1 text-xs text-gray-400";
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-x-3 gap-y-3">
      {/* row 1 */}
      <label className={labCls}>對象類型
        <select className={inputCls} disabled={subjectFixed} value={f.subject_type} onChange={e => set({ subject_type: e.target.value as FormState['subject_type'] })}>
          <option value="ip">全站 IP</option>
          <option value="ip_token">IP×連結</option>
          <option value="user">帳號</option>
        </select>
      </label>
      <label className={labCls}>
        {f.subject_type === 'user' ? '帳號名稱' : f.subject_type === 'ip_token' ? 'IP' : 'IP 位址'}
        <input className={inputCls} disabled={subjectFixed} placeholder={f.subject_type === 'user' ? '例 meowking' : '例 1.2.3.4'}
          value={f.subject_type === 'user' ? f.username : f.ip}
          onChange={e => set(f.subject_type === 'user' ? { username: e.target.value } : { ip: e.target.value })} />
      </label>
      <label className={labCls}>動作
        <select className={inputCls} value={f.action} onChange={e => set({ action: e.target.value as FormState['action'] })}>
          <option value="slow">慢速</option>
          <option value="block">429 封鎖</option>
        </select>
      </label>
      <label className={labCls}>範圍
        <select className={inputCls} value={f.scope}
          onChange={e => set({ scope: e.target.value as FormState['scope'] })}>
          <option value="transfer">僅傳輸</option>
          <option value="full">全站</option>
        </select>
      </label>
      {/* row 2 */}
      {f.scope === 'transfer' ? (
        <label className={labCls}>方向
          <select className={inputCls} value={f.direction}
            onChange={e => set({ direction: e.target.value as FormState['direction'] })}>
            <option value="both">上傳＋下載</option>
            <option value="up">僅上傳</option>
            <option value="down">僅下載</option>
          </select>
        </label>
      ) : <div className="hidden md:block" aria-hidden />}
      {f.action === 'slow' ? (
        <label className={labCls}>請求延遲（毫秒）
          <input type="number" min="0" className={inputCls}
            value={f.delay} onChange={e => set({ delay: e.target.value })} />
        </label>
      ) : <div className="hidden md:block" aria-hidden />}
      {f.action === 'slow' && (f.scope === 'full' || f.direction !== 'down') ? (
        <label className={labCls}>上傳頻寬上限（KB/秒）
          <input type="number" min="16" className={inputCls} value={f.upK} onChange={e => set({ upK: e.target.value })} />
        </label>
      ) : <div className="hidden md:block" aria-hidden />}
      {f.action === 'slow' && (f.scope === 'full' || f.direction !== 'up') ? (
        <label className={labCls}>下載頻寬上限（KB/秒）
          <input type="number" min="16" className={inputCls} value={f.dnK} onChange={e => set({ dnK: e.target.value })} />
        </label>
      ) : <div className="hidden md:block" aria-hidden />}
      {/* row 3 */}
      <label className={labCls}>期限
        <select className={inputCls} value={f.hours} onChange={e => set({ hours: e.target.value })}>
          <option value="1">1 小時</option>
          <option value="6">6 小時</option>
          <option value="24">24 小時</option>
          <option value="custom">自定義…</option>
          <option value="">無限期</option>
        </select>
      </label>
      {f.hours === 'custom' ? (
        <label className={labCls}>自定義到期（精準到秒）
          <input type="datetime-local" step="1" className={inputCls} value={f.customAt} onChange={e => set({ customAt: e.target.value })} />
        </label>
      ) : <div className="hidden md:block" aria-hidden />}
      <label className={labCls}>原因
        <input className={inputCls} placeholder="例：批量拖檔疑似外洩" value={f.reason} onChange={e => set({ reason: e.target.value })} />
      </label>
      <div aria-hidden className="hidden md:block" />
    </div>
  );
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

  const [form, setForm] = useState<FormState>(emptyForm);
  const [editRule, setEditRule] = useState<ControlRule | null>(null);
  const [editForm, setEditForm] = useState<FormState>(emptyForm);

  const setF = (patch: Partial<FormState>) => setForm(p => ({ ...p, ...patch }));
  const setE = (patch: Partial<FormState>) => setEditForm(p => ({ ...p, ...patch }));

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

  function validate(f: FormState): string | null {
    if (f.subject_type !== 'user' && !f.ip.trim()) return '請輸入 IP';
    if (f.subject_type === 'ip_token' && f.token.trim().length < 8) return '請輸入完整的連結 token（至少 8 字）';
    if (f.subject_type === 'user' && !f.username.trim()) return '請輸入帳號名稱';
    if (f.hours === 'custom' && !f.customAt) return '請選擇自定義到期時間';
    return null;
  }

  function create() {
    const err = validate(form);
    if (err) { setNotice({ text: err, ok: false }); return; }
    run(async () => {
      await ipControlApi.create(toBody(form));
      setForm({ ...emptyForm, subject_type: form.subject_type });
    }, '管控已新增');
  }

  function startEdit(r: ControlRule) {
    setEditRule(r);
    setEditForm({
      subject_type: r.subject_type,
      ip: r.ip_masked ?? '', token: r.token_prefix ?? '', username: r.username ?? '',
      action: r.action, scope: r.scope, direction: r.direction,
      delay: String(r.delay_ms ?? 0),
      upK: r.upload_kbps ? String(r.upload_kbps) : '',
      dnK: r.download_kbps ? String(r.download_kbps) : '',
      hours: r.expires_at ? 'custom' : '',
      customAt: r.expires_at ? localInputFromUtc(r.expires_at) : '',
      reason: r.reason ?? '',
    });
  }

  function saveEdit() {
    if (!editRule) return;
    // subject fields are immutable on edit; only the "action side" matters
    const err = editRule.subject_type === 'ip_token' && editForm.hours === 'custom' && !editForm.customAt ? '請選擇自定義到期時間' : null;
    if (err) { setNotice({ text: err, ok: false }); return; }
    run(async () => {
      await ipControlApi.update(editRule.id, {
        action: editForm.action,
        scope: editForm.scope,
        direction: editForm.scope === 'full' ? 'both' : editForm.direction,
        delay_ms: editForm.action === 'block' ? 0 : Number(editForm.delay) || 0,
        upload_kbps: (editForm.action !== 'block' && (editForm.scope === 'full' || editForm.direction !== 'down') && editForm.upK) ? Number(editForm.upK) : null,
        download_kbps: (editForm.action !== 'block' && (editForm.scope === 'full' || editForm.direction !== 'up') && editForm.dnK) ? Number(editForm.dnK) : null,
        expires_in_hours: (editForm.hours && editForm.hours !== 'custom') ? Number(editForm.hours) : null,
        expires_at: editForm.hours === 'custom' ? localToIso(editForm.customAt) : (editForm.hours === '' ? '' : null),
        reason: editForm.reason.trim() || undefined,
      });
      setEditRule(null);
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

  const statusPill = (r: ControlRule) => (
    <span className="flex flex-col gap-1">
      <span className={`inline-flex w-max items-center px-2 py-0.5 rounded-full text-xs font-medium ring-1 ${r.action === 'block' ? 'bg-red-900/30 text-red-400 ring-red-500/30' : 'bg-amber-900/30 text-amber-300 ring-amber-500/30'}`}>
        {r.action === 'block' ? '429 封鎖' : '慢速'}・{r.scope === 'full' ? '全站' : `傳輸・${r.direction === 'both' ? '上下' : r.direction === 'up' ? '上' : '下'}`}
      </span>
      {r.action === 'slow' && (
        <span className="text-xs text-gray-400">
          {r.delay_ms ? `${r.delay_ms}ms/請求` : ''}
          {r.upload_kbps ? `　↑${r.upload_kbps}KB/s` : ''}
          {r.download_kbps ? `　↓${r.download_kbps}KB/s` : ''}
        </span>
      )}
    </span>
  );

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

        {/* create form — fixed slots, never reflows */}
        <div className="mb-4 bg-gray-800/50 rounded-lg border border-gray-700 p-4">
          <FormFields f={form} set={setF} />
          <div className="mt-3 flex justify-end">
            <button onClick={create} disabled={busy}
              className="cursor-pointer px-5 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors">
              新增管控
            </button>
          </div>
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
                <th className="px-3 py-3 text-xs font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[14%]">到期</th>
                <th className="px-3 py-3 text-xs font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[20%]">近期帳號</th>
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
                  <td className={cell}>{statusPill(r)}</td>
                  <td className={cell}>{r.expires_at ? fmt(r.expires_at) : <span className="text-gray-500">無限期</span>}</td>
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
          處置台階：傳輸慢速 → 全站限速 → 全站 429 → 停用帳號。介面顯示的 IP 一律中段遮罩。
        </p>
      </div>

      {/* edit modal — table rows never reflow */}
      {editRule && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="fixed inset-0 bg-black/60" onClick={() => setEditRule(null)}></div>
          <div className="relative z-10 w-[94vw] max-w-2xl max-h-[88vh] overflow-y-auto scrollbar-hide rounded-lg shadow-xl bg-gray-800 p-5">
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-lg font-semibold">編輯管控 #{editRule.id}｜{subjectLabel(editRule)}</h3>
              <button onClick={() => setEditRule(null)} className="p-1 text-gray-400 hover:text-white cursor-pointer"><X className="w-5 h-5" /></button>
            </div>
            <p className="text-xs text-gray-500 mb-4">對象不可更改；如需換對象請解除後重建。</p>
            <FormFields f={editForm} set={setE} subjectFixed />
            <div className="mt-4 flex justify-end gap-2">
              <button onClick={() => setEditRule(null)} className="px-4 py-2 rounded bg-gray-600 hover:bg-gray-500 cursor-pointer text-sm">取消</button>
              <button onClick={saveEdit} disabled={busy} className="px-4 py-2 rounded bg-green-600 hover:bg-green-700 disabled:opacity-50 cursor-pointer text-sm">儲存</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function localInputFromUtc(iso: string): string {
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
  if (Number.isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export default IPManagement;
