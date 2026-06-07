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
  if (!adminUser) return null;

  return (
    <div className={`bg-gray-900 text-white p-6 ${layoutClass}`}>
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
      <table>
        <thead>
          <tr>
            <th>Username</th>
            <th>Email</th>
            <th>Used</th>
            <th>Quota</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u: UserInfo) => (
            <tr key={u.id}>
              <td>{u.username}</td>
              <td>{u.email}</td>
              <td>{u.used_storage}</td>
              <td>{u.total_storage}</td>
              <td>{u.online ? "On" : "Off"}{u.enabled ? " En" : " Dis"}</td>
              <td>
                <button onClick={() => { adminApi.forceLogout(u.id); }}>Logout</button>
                <button onClick={() => { adminApi.toggleEnabled(u.id); loadUsers(); }}>Toggle</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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