import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Pencil, Trash2, Power, PowerOff } from "lucide-react";
import { announcementApi, type AnnouncementRow } from "../../api/announcementApi";
import { invalidateAnnouncements } from "../../store/announcements";
import { authApi } from "../../api/authApi";

interface Props {
  layoutClass?: string;
}

const MAX_LEN = 500;

function fmtUtc(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
  return d.toLocaleString('zh-TW', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function toIsoLocalInput(utcIso: string | null): string {
  if (!utcIso) return '';
  const d = new Date(utcIso.endsWith('Z') ? utcIso : utcIso + 'Z');
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function AnnouncementManagement({ layoutClass = "" }: Props) {
  const nav = useNavigate();
  const [loading, setLoading] = useState(true);
  const [adminUser, setAdminUser] = useState(false);
  const [rows, setRows] = useState<AnnouncementRow[]>([]);
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const [newContent, setNewContent] = useState('');
  const [newHasExpiry, setNewHasExpiry] = useState(false);
  const [newExpiry, setNewExpiry] = useState('');

  const [editId, setEditId] = useState<number | null>(null);
  const [editContent, setEditContent] = useState('');
  const [editHasExpiry, setEditHasExpiry] = useState(false);
  const [editExpiry, setEditExpiry] = useState('');

  useEffect(() => {
    authApi.checkSession().then((s: any) => {
      if (s.authenticated && s.identity === 1) { setAdminUser(true); setLoading(false); }
      else nav("/login");
    });
  }, [nav]);

  const load = useCallback(async () => {
    try { setRows(await announcementApi.adminList()); } catch (e) { console.error(e); }
  }, []);

  useEffect(() => { if (adminUser) load(); }, [adminUser, load]);

  async function guard(fn: () => Promise<void>, okMsg: string) {
    if (busy) return;
    setBusy(true); setNotice(null);
    try {
      await fn();
      setNotice({ text: okMsg, ok: true });
      await load();
      invalidateAnnouncements();
    } catch (e: any) {
      setNotice({ text: e?.message ?? '操作失敗', ok: false });
    }
    setBusy(false);
  }

  function create() {
    const c = newContent.trim();
    if (!c) { setNotice({ text: '請輸入公告內容', ok: false }); return; }
    if (c.length > MAX_LEN) { setNotice({ text: `公告內容最多 ${MAX_LEN} 字`, ok: false }); return; }
    if (newHasExpiry && !newExpiry) { setNotice({ text: '請指定截止時間，或改用無限期', ok: false }); return; }
    guard(async () => {
      await announcementApi.create({ content: c, expires_at: newHasExpiry ? newExpiry : null });
      setNewContent(''); setNewHasExpiry(false); setNewExpiry('');
    }, '公告已新增');
  }

  function startEdit(r: AnnouncementRow) {
    setEditId(r.id);
    setEditContent(r.content);
    setEditHasExpiry(!!r.expires_at);
    setEditExpiry(toIsoLocalInput(r.expires_at));
  }

  function saveEdit(id: number) {
    const c = editContent.trim();
    if (!c || c.length > MAX_LEN) { setNotice({ text: `公告內容需為 1-${MAX_LEN} 字`, ok: false }); return; }
    if (editHasExpiry && !editExpiry) { setNotice({ text: '請指定截止時間，或改用無限期', ok: false }); return; }
    guard(async () => {
      await announcementApi.update(id, { content: c, expires_at: editHasExpiry ? editExpiry : '' });
      setEditId(null);
    }, '公告已更新');
  }

  function toggleEnabled(r: AnnouncementRow) {
    guard(async () => { await announcementApi.update(r.id, { enabled: !r.enabled }); },
      r.enabled ? '公告已停用' : '公告已啟用');
  }

  function remove(r: AnnouncementRow) {
    if (!window.confirm(`確定刪除公告「${r.content.slice(0, 20)}…」？`)) return;
    guard(async () => { await announcementApi.remove(r.id); }, '公告已刪除');
  }

  const statusPill = (r: AnnouncementRow) => r.effective
    ? <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ring-1 bg-green-900/30 text-green-400 ring-green-500/30">Active</span>
    : r.enabled && r.expired
      ? <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ring-1 bg-gray-700/50 text-gray-400 ring-gray-500/30">已到期</span>
      : <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ring-1 bg-red-900/30 text-red-400 ring-red-500/30">Disabled</span>;

  if (loading || !adminUser) return null;

  return (
    <div className={`flex flex-col min-h-screen text-white p-4 sm:p-6 ${layoutClass}`}>
      <div className="w-full max-w-7xl mx-auto mt-[1%] flex-1">
        <div className="mb-4 flex flex-col sm:flex-row justify-between items-center gap-2">
          <h2 className="text-xl font-semibold text-cyan-400 uppercase tracking-wider">Announcement</h2>
          {notice && (
            <span className={`px-3 py-1 rounded-full text-xs font-medium ring-1 ${notice.ok ? "bg-green-900/30 text-green-400 ring-green-500/30" : "bg-red-900/30 text-red-400 ring-red-500/30"}`}>
              {notice.text}
            </span>
          )}
        </div>

        {/* create row */}
        <div className="mb-4 bg-gray-800/50 rounded-lg border border-gray-700 p-3 flex flex-col md:flex-row gap-2 items-stretch md:items-center">
          <input
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder={`新公告內容（最多 ${MAX_LEN} 字）`}
            maxLength={MAX_LEN}
            className="flex-1 bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:outline-none focus:ring-1 focus:ring-green-500"
          />
          <label className="flex items-center gap-1 text-sm text-gray-300 cursor-pointer whitespace-nowrap">
            <input type="checkbox" checked={newHasExpiry} onChange={(e) => setNewHasExpiry(e.target.checked)} />
            設截止時間
          </label>
          {newHasExpiry && (
            <input type="datetime-local" value={newExpiry} onChange={(e) => setNewExpiry(e.target.value)}
              className="bg-gray-700 text-white px-2 py-1.5 rounded border border-gray-600 text-sm" />
          )}
          <button onClick={create} disabled={busy}
            className="cursor-pointer px-4 py-2 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-sm font-medium rounded transition-colors whitespace-nowrap">
            新增公告
          </button>
        </div>

        <div className="w-full rounded-lg border border-gray-700 bg-gray-800/50 overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr>
                <th className="px-4 py-3 text-base font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[40%]">內容</th>
                <th className="px-4 py-3 text-base font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[10%] text-center">狀態</th>
                <th className="px-4 py-3 text-base font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[15%] hidden md:table-cell">建立時間</th>
                <th className="px-4 py-3 text-base font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[15%]">截止時間</th>
                <th className="px-4 py-3 text-base font-semibold uppercase tracking-wider text-cyan-400 bg-gray-800 w-[20%] text-center">操作</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.id} className="border-b border-gray-700/50 hover:bg-gray-800/50 transition-colors align-top">
                  <td className="px-4 py-3 text-sm">
                    {editId === r.id ? (
                      <div className="flex flex-col gap-2">
                        <input value={editContent} onChange={(e) => setEditContent(e.target.value)} maxLength={MAX_LEN}
                          className="bg-gray-700 text-white px-2 py-1.5 rounded border border-gray-600 text-sm" />
                        <label className="flex items-center gap-1 text-xs text-gray-300 cursor-pointer">
                          <input type="checkbox" checked={editHasExpiry} onChange={(e) => setEditHasExpiry(e.target.checked)} />
                          設截止時間
                        </label>
                        {editHasExpiry && (
                          <input type="datetime-local" value={editExpiry} onChange={(e) => setEditExpiry(e.target.value)}
                            className="bg-gray-700 text-white px-2 py-1 rounded border border-gray-600 text-xs" />
                        )}
                        <span className="flex gap-2">
                          <button onClick={() => saveEdit(r.id)} className="cursor-pointer px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-xs rounded">儲存</button>
                          <button onClick={() => setEditId(null)} className="cursor-pointer px-3 py-1 bg-red-600 hover:bg-red-700 text-white text-xs rounded">取消</button>
                        </span>
                      </div>
                    ) : (
                      <span className="break-words whitespace-normal">{r.content}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-center">{statusPill(r)}</td>
                  <td className="px-4 py-3 text-sm text-gray-300 hidden md:table-cell whitespace-nowrap">{fmtUtc(r.created_at)}</td>
                  <td className="px-4 py-3 text-sm text-gray-300 whitespace-nowrap">{r.expires_at ? fmtUtc(r.expires_at) : <span className="text-gray-500">無限期</span>}</td>
                  <td className="px-4 py-3">
                    <span className="flex items-center justify-center gap-3">
                      <Pencil className="w-5 h-5 text-cyan-300 cursor-pointer" onClick={() => startEdit(r)} />
                      {r.enabled
                        ? <PowerOff className="w-5 h-5 text-red-400 cursor-pointer" onClick={() => toggleEnabled(r)} />
                        : <Power className="w-5 h-5 text-green-400 cursor-pointer" onClick={() => toggleEnabled(r)} />}
                      <Trash2 className="w-5 h-5 text-red-500 cursor-pointer" onClick={() => remove(r)} />
                    </span>
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500 text-sm">目前沒有公告，使用上方欄位新增第一條。</td></tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-xs text-gray-500">生效中的公告會以跑馬燈顯示於所有登入使用者的導覽列（上限 20 條）；截止時間到會自動消失。</p>
      </div>
    </div>
  );
}

export default AnnouncementManagement;
