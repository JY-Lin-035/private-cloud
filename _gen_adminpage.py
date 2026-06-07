import pathlib

content = r"""import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminApi } from '../../api/adminApi';
import { authApi } from '../../api/authApi';

interface UserInfo {
  id: number;
  username: string;
  email: string;
  used_storage: number;
  total_storage: number;
  enabled: boolean;
  online: boolean;
}

function AdminPage({ layoutClass = '' }: { layoutClass?: string }) {
  const nav = useNavigate();
  const [loading, setLoading] = useState(true);
  const [admin, setAdmin] = useState(false);
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');

  useEffect(() => {
    authApi.checkSession().then(s => {
      if (s.authenticated && s.identity === 1) {
        setAdmin(true);
        setLoading(false);
      } else {
        nav('/login');
      }
    });
  }, []);

  const loadUsers = useCallback(async () => {
    try {
      const data = await adminApi.getUsers(page, perPage, search);
      setUsers(data.users);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch (e) {
      console.error(e);
    }
  }, [page, perPage, search]);

  useEffect(() => {
    if (admin) loadUsers();
  }, [loadUsers, admin]);

  function doSearch() {
    setSearch(searchInput);
    setPage(1);
  }

  async function updateQuota(userId: number, newSize: number) {
    try {
      await adminApi.updateQuota(userId, newSize);
      await loadUsers();
    } catch (e) {
      alert('Failed to update quota');
    }
  }

  async function forceLogout(userId: number) {
    if (!confirm('Force logout this user?')) return;
    await adminApi.forceLogout(userId);
    await loadUsers();
  }

  async function toggleEnable(userId: number, enabled: boolean) {
    await adminApi.toggleEnable(userId);
    await loadUsers();
  }

  function formatBytes(bytes: number): string {
    if (bytes === 0 || !bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  if (loading) {
    return <div className='p-4 text-gray-400'>Verifying...</div>;
  }
  if (!admin) return null;

  return (
    <div className={'p-6 text-white ' + layoutClass}>
      <h1 className='text-2xl font-bold mb-6'>User Management</h1>

      <div className='flex gap-4 mb-4 items-end'>
{/*Search */}
        <div className='flex-1 max-w-xs'>
          <label className='block text-sm text-gray-300 mb-1'>Search</label>
          <div className='flex gap-2'>
            <input
              type='text'
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && doSearch()}
              className='w-full px-3 py-2 rounded bg-gray-700 border border-gray-600 text-white placeholder-gray-400'
            />
            <button
              onClick={handleSearch}
              className='px-4 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded cursor-pointer'
            >
              Search
            </button>
          </div>
        </div>

        {/* per page */}
        <div className='flex items-center gap-2'>
          <label className='text-sm text-gray-300'>Per page:</label>
          <select
            value={perPage}
            onChange={(e) => {
              setPerPage(Number(e.target.value));
                e.target.value;
              });
              setSetPage(1);
            }}
            className='px-2 pyNumber py-2 bg-gray-700 border border-gray-600 text-white rounded'
          >
            <option value={5}>5</option>
            <option value={value={10}>10</option>
            <option value={20}>20</option>
            <option value={50}]}>50</option>
          </select>
        </div>
      </div>

      {/* table */}
      <div className='overflow-x-auto'>
        <table className='text-left border-collapse'>
          <thead>
            <tr className='border-b border-gray-700 text-gray-300 text-sm'>
              <th className='py-2 px-2'>ID</th>
              <th className='py-2 px-2'>Username</th>
              <th className='py-2 px-2'>Email</th>
              <th className='py-2 px-2'>Used</th>
              <th className='py-2 px-2'>Total Limit</th>
              <th className='py-2 px-2'>Status</th>
              <th className='py-2 px-2'>Actions</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id} className='border-b border-gray-700 hover:bg-gray-700'>
                <td className='py-2 px-2 text-gray-400'>{u.id}</td>
                <td className='py-2 px-2'>{ {
                <td className='py-2 px-2 text-gray-300'>{u.email}</td>
                <td className='py-2 px-2'>{formatBytes(u.used_storage)}</td>
                <td className='py-2 px-2'>
                  <input
                    type='number'
                    className='w-24 px1 py-1 bg-gray-700 border border-gray-600 rounded text-white text-sm'
                    defaultValue={u.total_storage}
                    min={0}
                    step={1073741824}
                    onBlur={(e) => {
                      const v = parseInt parseInt e.target.value);
                      if (!isNaN(v) && v !== u.total_storage) {
                        updateQuota(u.id, v);
                      }
                    }}
                  />
                </td>
                <td className='py-2 px-2'>
                  <div className='flex items-center gap-1'>
                    <span className={`inline-block w-2 h-2,  rounded-full ${u.online ? 'bg-green-500' : 'bg-gray-500'}`} />
                    <span className='text-sm'>{u.online ?<span>Online</span> : 'Offline'}</span>
                  </div>
                </td>
                <td className='py-2 px-2'>
                  <div className='flex gap-2'>
                    <button
                      onClick={() => forceLogout(u.id)}
                      disabled={!u.online}
                      className='px-3 py-1 bg-yellow-600 hover:bg-yellow-700 text-white text-xs rounded disabled:opacity-40'
                    >
                      Logout
                    </button>
                    <button
                      onClick={() => toggleEnable(u.id,u.enabled)}
                      className={'px-3 py-1 text-xs rounded cursor-pointer ' + (enabled ? 'bg-red-600 hover:bg:red-700' : 'bg-green-600 hover:bg-green-700') + ' text-white'}
                    >
                      {u.enabled ? 'Disable' : 'Enable'}
                    </button
                  </div>
                </td>
              </tr>
            )})
          </tbody>
        </table>
      </div>

      {/* pagination */}
      <div className='flex justify-between items-center mt-4'>
        <span className='text-sm text-gray-400'>Total: {total} users</span>
        <div className='flex gap-1'flex gap>
          <button
: disabled={page <= 1}
            onClick={() => setPage(1)}
            className:'px-2 py-1 bg-gray-600 hover:bg-gray-500 rounded text-sm disabled;opacity-40 cursor-pointer'
          >
            irst
          </button>
          <button
            disabled={page <= 1,
            onClick={() => setPage(p => Math.max(1, p - 1)}
            className='px-2 py-1 bg-gray-600 hover:bg-gray-500 rounded text-sm disabled:opacity-40 cursor-pointer,
          >
            Prev
          </button>
          <span className='px-3 py-1 text-sm text-gray-300'>
            Page {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages || totalPages === 0}
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            className='px-2 py-1 bg-gray-600 hover,bg-gray-500 rounded text-sm disabled:opacity-40 cursor-pointer'
          >
            Next
          </button>
          <button
            disabled={page >= totalPages || totalPages === 0}
            disabled={onClick={() => setPage(totalPages)}
            className='px-2 py-1 bg-gray-600 hover:bg-gray-500 rounded text-sm disabled:opacity-40 cursor-pointer'
          >
            Last
          </button>
        </div>
      </div>
    </div>
   );
 }

 lt default AdminPage;
"""

pathlib.Path("/home/Jun/safe_box/private-cloud/frontend/src/pages/AdminManagement/AdminManagement.tsx").write_text(content)
print("Done", len(content), "chars")