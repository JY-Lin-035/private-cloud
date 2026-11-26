import { useCallback, useEffect, useMemo, useState } from "react";
import { ipControlApi } from "../../api/ipControlApi";
import type { PolicyGroup, PolicyItem, PolicyVersion } from "../../api/ipControlApi";

/**
 * 風控門檻頁籤（round 24 PR④）。
 *
 * 「門檻」= 未來如何判定（版本化、可回溯）；「規則」= 目前已生效的限制。
 * 這一頁只改判定標準：不重計已開的窗、不解除既有封鎖（後端已保證，
 * 這裡的文案也要講清楚，避免管理員以為改完就等於馬上生效）。
 */

const SOURCE_STYLE: Record<string, string> = {
  '程式預設': 'text-gray-400',
  '部署設定': 'text-sky-300',
  '管理員覆寫': 'text-amber-300',
};

export default function PolicyThresholds() {
  const [groups, setGroups] = useState<PolicyGroup[]>([]);
  const [version, setVersion] = useState<number | null>(null);
  const [history, setHistory] = useState<PolicyVersion[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [resetIds, setResetIds] = useState<string[]>([]);
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; ok: boolean } | null>(null);

  const apply = useCallback((data: { version: number; groups: PolicyGroup[] }) => {
    setGroups(data.groups);
    setVersion(data.version);
  }, []);

  const load = useCallback(() => ipControlApi.policies(), []);
  const loadHistory = useCallback(() => ipControlApi.policyHistory().catch(() => [] as PolicyVersion[]), []);

  useEffect(() => {
    let alive = true;
    void load().then((data) => alive && apply(data)).catch(() => alive && setNotice({ text: '讀取門檻失敗', ok: false }));
    void loadHistory().then((h) => alive && setHistory(h));
    return () => { alive = false; };
  }, [load, loadHistory, apply]);

  const reload = useCallback(() => {
    void load().then(apply).catch(() => setNotice({ text: '讀取門檻失敗', ok: false }));
    void loadHistory().then(setHistory);
  }, [load, loadHistory, apply]);

  const items = useMemo(() => {
    const map: Record<string, PolicyItem> = {};
    groups.forEach((g) => g.items.forEach((it) => { map[it.id] = it; }));
    return map;
  }, [groups]);

  const diff = useMemo(() => {
    const rows: { id: string; label: string; before: number; after: number | 'default'; unit: string }[] = [];
    Object.entries(drafts).forEach(([id, raw]) => {
      const item = items[id];
      if (!item) return;
      const after = raw === '' ? 'default' as const : Number(raw);
      if (after === 'default' ? item.source !== '管理員覆寫' : after === item.value) return;
      rows.push({ id, label: item.label, before: item.value, after, unit: item.unit });
    });
    resetIds.filter((id) => !(id in drafts)).forEach((id) => {
      const item = items[id];
      if (item && item.source === '管理員覆寫') {
        rows.push({ id, label: item.label, before: item.value, after: 'default', unit: item.unit });
      }
    });
    return rows;
  }, [drafts, resetIds, items]);

  const conflict = (err: unknown) => {
    const status = (err as { response?: { status?: number } })?.response?.status;
    const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
    if (status === 409) {
      setNotice({ text: `${detail || '設定已被其他頁面更新'}（未儲存的要求已保留在下方）`, ok: false });
      return true;
    }
    setNotice({ text: detail || '儲存失敗', ok: false });
    return false;
  };

  const save = async () => {
    if (version === null || (diff.length === 0)) return;
    setBusy(true);
    setNotice(null);
    try {
      const changes: Record<string, number> = {};
      Object.entries(drafts).forEach(([id, raw]) => { if (raw !== '') changes[id] = Number(raw); });
      if (Object.keys(changes).length) {
        await ipControlApi.updatePolicies({ changes, expected_version: version, reason: reason.trim() || undefined });
      }
      const toReset = resetIds.filter((id) => drafts[id] === undefined);
      if (toReset.length) {
        await ipControlApi.resetPolicies({ ids: toReset, expected_version: version, reason: reason.trim() || '恢復預設' });
      }
      setDrafts({});
      setResetIds([]);
      setReason('');
      setNotice({ text: '已生效（新門檻只影響之後的判定）', ok: true });
      reload();
    } catch (e) {
      conflict(e);
    } finally {
      setBusy(false);
    }
  };

  const rollback = async (to: number) => {
    if (version === null) return;
    setBusy(true);
    try {
      await ipControlApi.rollbackPolicy({ to_version: to, expected_version: version, reason: `回滾至 v${to}` });
      setNotice({ text: `已回滾，建立新版本`, ok: true });
      reload();
    } catch (e) {
      conflict(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="text-xs text-gray-400 leading-relaxed">
        這裡是<span className="text-gray-200">判定標準（門檻）</span>，不是目前生效的處分；
        既有封鎖、慢速規則與已開窗的計數<span className="text-gray-200">不會被重設</span>。
        有效值優先序：管理員覆寫 → 部署設定 → 程式預設。nginx／Cloudflare 限制、檔案大小與儲存配額不在本頁。
      </div>

      <div className="flex items-center gap-2 text-xs">
        <span className="text-gray-400">目前版本 v{version ?? '-'}</span>
        <button onClick={() => setShowHistory((v) => !v)}
          className="px-2 py-1 rounded bg-gray-700 text-gray-200 cursor-pointer hover:bg-gray-600">
          {showHistory ? '收合歷史' : '查看歷史與回滾'}
        </button>
        <button onClick={() => { reload(); setNotice(null); }}
          className="px-2 py-1 rounded bg-gray-700 text-gray-200 cursor-pointer hover:bg-gray-600">重新載入</button>
        {notice && (
          <span className={notice.ok ? 'text-green-400' : 'text-red-400'}>{notice.text}</span>
        )}
      </div>

      {showHistory && (
        <div className="border border-gray-600 rounded bg-gray-800/60 p-2 max-h-56 overflow-auto">
          {history.length === 0 && <div className="text-xs text-gray-500">尚無版本紀錄（尚未有人覆寫門檻）</div>}
          {history.map((h) => (
            <div key={h.version} className="text-xs text-gray-300 border-b border-gray-700 last:border-0 py-1.5 flex items-start gap-2">
              <span className="text-gray-500 shrink-0 w-24">{new Date(h.created_at).toLocaleString('zh-TW', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</span>
              <span className="shrink-0 w-8">v{h.version}</span>
              <span className="shrink-0 text-gray-500">{h.action === 'rollback' ? '回滾' : h.action === 'reset' ? '恢復預設' : '修改'}｜{h.actor || '-'}</span>
              <span className="flex-1 min-w-0 break-words">
                {h.reason ? `${h.reason}｜` : ''}
                {Object.values(h.changed).map((c) => `${c.label}:${c.before}→${c.after}`).join('、') || '無實際變更'}
              </span>
              <button disabled={busy} onClick={() => void rollback(h.version)}
                className="shrink-0 px-2 py-0.5 rounded bg-gray-700 hover:bg-gray-600 cursor-pointer disabled:opacity-50">
                回滾至此
              </button>
            </div>
          ))}
        </div>
      )}

      {groups.map((group) => (
        <div key={group.name} className="border border-gray-600 rounded overflow-hidden">
          <div className="px-3 py-1.5 bg-gray-700/70 text-gray-200 text-sm">{group.name}</div>
          <table className="w-full text-left text-xs">
            <thead className="text-gray-500">
              <tr>
                <th className="px-3 py-1 font-normal">項目</th>
                <th className="px-2 py-1 font-normal">有效值</th>
                <th className="px-2 py-1 font-normal">來源</th>
                <th className="px-2 py-1 font-normal">計數對象</th>
                <th className="px-2 py-1 font-normal">時間窗語義</th>
                <th className="px-2 py-1 font-normal">觸發動作</th>
                <th className="px-2 py-1 font-normal">備註／依賴</th>
              </tr>
            </thead>
            <tbody>
              {group.items.map((it) => {
                const edited = it.id in drafts;
                const resetting = resetIds.includes(it.id);
                return (
                  <tr key={it.id} className="border-t border-gray-700 align-top">
                    <td className="px-3 py-1.5 text-gray-200">{it.label}</td>
                    <td className="px-2 py-1.5 whitespace-nowrap">
                      {it.editable ? (
                        <span className="inline-flex items-center gap-1">
                          <input
                            type="number"
                            value={edited ? drafts[it.id] : (resetting ? '' : String(it.value))}
                            placeholder="預設"
                            min={it.min}
                            max={it.max}
                            onChange={(e) => {
                              const v = e.target.value;
                              setDrafts((d) => { const n = { ...d }; if (v === '') delete n[it.id]; else n[it.id] = v; return n; });
                              setResetIds((r) => r.filter((x) => x !== it.id));
                            }}
                            className="w-24 bg-gray-700 text-white px-1.5 py-1 rounded border border-gray-600 focus:outline-none focus:ring-1 focus:ring-cyan-500"
                          />
                          <span className="text-gray-500">{it.unit}</span>
                          {it.source === '管理員覆寫' && (
                            <button title="恢復預設"
                              onClick={() => {
                                setDrafts((d) => { const n = { ...d }; delete n[it.id]; return n; });
                                setResetIds((r) => (r.includes(it.id) ? r : [...r, it.id]));
                              }}
                              className="px-1 rounded bg-gray-700 text-gray-300 hover:bg-gray-600 cursor-pointer">↺</button>
                          )}
                        </span>
                      ) : (
                        <span className="text-gray-400">{it.value} {it.unit}<span className="ml-1 text-gray-600">（唯讀）</span></span>
                      )}
                    </td>
                    <td className={`px-2 py-1.5 whitespace-nowrap ${SOURCE_STYLE[it.source] ?? 'text-gray-300'}`}>{it.source}</td>
                    <td className="px-2 py-1.5 text-gray-400">{it.subject}</td>
                    <td className="px-2 py-1.5 text-gray-400">{it.window}</td>
                    <td className="px-2 py-1.5 text-gray-400">{it.action}</td>
                    <td className="px-2 py-1.5 text-gray-500">
                      {it.route ? <code className="text-gray-400">{it.method} {it.route}</code> : null}
                      {it.route && (it.depends || it.note) ? <span className="text-gray-600">｜</span> : null}
                      {it.depends || it.note}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ))}

      {diff.length > 0 && (
        <div className="border border-cyan-700/60 bg-cyan-900/20 rounded p-3">
          <div className="text-sm text-cyan-200 mb-2">儲存前確認（{diff.length} 項變更）</div>
          <ul className="text-xs text-gray-300 list-disc pl-5 mb-2">
            {diff.map((d) => (
              <li key={d.id}>{d.label}：{d.before} → {d.after === 'default' ? '預設' : `${d.after} ${d.unit}`}</li>
            ))}
          </ul>
          <div className="flex flex-wrap items-center gap-2">
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="變更理由（寫入稽核）"
              className="flex-1 min-w-[200px] bg-gray-700 text-white px-2 py-1.5 rounded border border-gray-600 text-sm focus:outline-none focus:ring-1 focus:ring-cyan-500" />
            <button disabled={busy} onClick={() => void save()}
              className="px-3 py-1.5 rounded bg-cyan-600 text-white text-sm cursor-pointer hover:bg-cyan-500 disabled:opacity-50">
              {busy ? '處理中…' : `儲存為 v${(version ?? 0) + 1}`}
            </button>
            <button disabled={busy} onClick={() => { setDrafts({}); setResetIds([]); }}
              className="px-3 py-1.5 rounded bg-gray-700 text-gray-200 text-sm cursor-pointer hover:bg-gray-600">
              還原未儲存
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
