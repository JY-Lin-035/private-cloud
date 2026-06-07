import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { adminApi, type UserInfo } from "../../api/adminApi";
import { authApi } from "../../api/authApi";

interface Props {
  layoutClass?: string;
}

function AdminPage({ layoutClass = "" }: Props) {
  const nav = useNavigate();
  const [loading, setLoading] = useState(true);
  const [adminUser, setAdminUser] = useState(false);
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [editingQuota, setEditingQuota] = useState<number | null>(null);
  const [quotaEdits, setQuotaEdits] = useState<Record<number, string>>({});

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

  const loadUsers = useCallback(async () => {
    try {
      const res = await adminApi.getUsers(page, perPage, search);
      setUsers(res.users);
      setTotal(res.total);
      setTotalPages(res.total_pages);
    } catch (e) {
      console.error(e);
    }
  }, [page, perPage, search]);

  useEffect(() => {
    if (adminUser) loadUsers();
  }, [loadUsers, adminUser]);

  if (loading) return <div>Loading...</div>;

    function formatBytes(b: number): string {
      if (!b || b === 0) return "0 B";
      const units = ["B", "KB", "MB", "GB", "TB"];
      let i = 0;
      let v = b;
      while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
      const n = v < 10 ? v.toFixed(1) : v.toFixed(0);
      return n + " " + units[i];
    }

    if (!adminUser) return null;

  return (
    <div className={`min-h-screen bg-gray-900 text-white p-6 ${layoutClass}`}>
      <h1>User Management</h1>
      <input value={searchInput} onChange={(e) => setSearchInput(e.target.value)} placeholder="Search" />
      <button onClick={() => { setSearch(searchInput); setPage(1); loadUsers(); }}>Search</button>
      <span>Total: {total}</span>
      <select value={perPage} onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1); }}>
        <option value={5}>5</option>
        <option value={10}>10</option>
        <option value={20}>20</option>
        <option value={50}>50</option>
      </select>
      <div className="flex justify-center w-full"><div className="cursor-pointer w-[70vw] overflow-x-auto rounded-lg border border-gray-700 bg-gray-800/50"><table className="w-full table-fixed text-center">
        <thead>
          <tr>
            <th className="text-center px-6 py-3 text-sm font-semibold uppercase tracking-wider text-gray-400 w-[18%]">Username</th>
            <th className="text-center px-6 py-3 text-sm font-semibold uppercase tracking-wider text-gray-400 w-[24%]">Email</th>
            <th className="text-center px-6 py-3 text-sm font-semibold uppercase tracking-wider text-gray-400 w-[12%]">Used</th>
            <th className="text-center px-6 py-3 text-sm font-semibold uppercase tracking-wider text-gray-400 w-[250px]">Quota</th>
            <th className="text-center px-6 py-3 text-sm font-semibold uppercase tracking-wider text-gray-400 w-[12%]">Status</th>
            <th className="text-center px-6 py-3 text-sm font-semibold uppercase tracking-wider text-gray-400 w-[18%]">Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u: UserInfo) => (
            <tr className="hover:bg-gray-800/50 transition-colors border-b border-gray-700/50" key={u.id}>
              <td>{u.username}</td>
              <td>{u.email}</td>
              <td>{formatBytes(u.used_storage)}</td>
              <td>
                {editingQuota === u.id ? (
                  <span className="inline-flex items-center justify-center gap-2 min-w-[160px]">
                    <input
                      value={quotaEdits[u.id] ?? u.total_storage}
                      onChange={(e) => setQuotaEdits(p => ({ ...p, [u.id]: e.target.value }))}
                      type="number"
                      min="0"
                      className="cursor-pointer w-48 bg-gray-700 text-white px-2 py-1 rounded text-sm border border-gray-600 focus:outline-none focus:ring-1 focus:ring-green-500"
                    />
                    <button onClick={async () =>  {
                                            const n = Number(quotaEdits[u.id]);
                                            if (!isNaN(n) && n >= 0) {
                                              await adminApi.updateQuota(u.id, n);
                                            }
                                            setEditingQuota(null);
                                            loadUsers();
                                          }} className="cursor-pointer px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded transition-colors">Save</button>
                                          <button onClick={() => setEditingQuota(null)} className="cursor-pointer px-3 py-1 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded transition-colors">X</button>
                  </span>
                ) : (
                  <span className="inline-flex items-center justify-center gap-2 min-w-[160px]">{formatBytes(u.total_storage)} <button onClick={() => setEditingQuota(u.id)} className="cursor-pointer px-3 py-1 bg-green-600 hover:bg-green-700 text-white text-sm font-medium rounded transition-colors">Edit</button></span>
                )}
              </td>
              <td className="text-center px-6 py-4">
                              <span className={`cursor-pointer inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium ring-1 ${u.online ? "bg-green-900/30 text-green-400 ring-green-500/30" : u.enabled ? "bg-red-900/30 text-red-400 ring-red-500/30" : "bg-red-900/30 text-red-400 ring-red-500/30"}`}>
                                {u.online ? "Online" : u.enabled ? "Offline" : "Disabled"}
                              </span>
                            </td>
              <td className="text-center px-6 py-4">
                              <div className="flex items-center justify-center gap-2">
                                {u.online && (
                                  <button onClick={() => { adminApi.forceLogout(u.id); loadUsers(); }} className="cursor-pointer px-3 py-1 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded transition-colors">Logout</button>
                                )}
                                <button onClick={() => { adminApi.toggleEnabled(u.id); loadUsers(); }} className={`cursor-pointer px-3 py-1 text-sm font-medium rounded transition-colors ${u.enabled ? "bg-red-600 hover:bg-red-700 text-white" : "bg-green-600 hover:bg-green-700 text-white"}`}>{u.enabled ? "Disable" : "Enable"}</button>
                              </div>
                            </td>
            </tr>
          ))}
        </tbody>
      </table></div></div>
      {totalPages > 1 && (
        <div>
          <button disabled={page <= 1} onClick={() => setPage(page - 1)}>Prev</button>
          <span>Page {page} of {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </div>
  );
}

export default AdminPage;