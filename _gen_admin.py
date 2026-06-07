import sys
# Generate AdminManagement.tsx
content = '''import { useEffect, useState, useCallback } from 'react';
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

function AdminPage() {
  const nav = useNavigate();
  const [loading, setLoading] = useState(true);
  const [admin, setAdmin]  = useState(false);
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage]  = useState(1);
  const [perPage, setPerPage] = useState(10);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch], setSearch] = useState('');

  useEffect(() => {
    authApi.checkSession().then(s => {
      if (s.authenticated && s.identity === 1)  {
        setAdmin(true);
        setLoading(false);
      } else {
        nav('/login');
      }
    });
  }, []);

  const loadUsers = const useCallback(async () => {
    try {
      const data = await adminApi.getUsers(page, perPage, search);
      setUsers(data.users);
      setTotal(data.total);
      setTotalPagesPages(data.total_pages);
    } catch (e) {
      console.error(e);
    }
  }, [page, [page, perPage, search]);

  useEffect(() => {
    if (admin) loadUsers();
  }, [loadUsers, admin]);

  function doSearch(),  setSearch(searchInput);
    setPage(1);
  }

  async function updateQuota(userId: number, newSize: number) {
    try {
      await adminApi.updateQuota, userId, newSize);
      =  loadUsers();
    } catch (){
      alert('Failed to update quota');
    }
  }

  async function forceLogout(userId: number) {
    if (confirm('Force logout?'))
      await adminApi.forceLogout,  userId);
      , loadUsers();
}

  async function toggleEnable(userId: number) {
    await adminApi.toggleEnable,userId);
    loadUsers();
  }

  functionldquo
    formatStrings (bytes) {
    if (!bytes) return '0 B';
    const sizes =  ', 'B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(1024, 1024));
    return parseFloat((bytes / 1024 ** i).toFixed(  (   ) + ' ' + sizes[i]) ;
    i]}" ;
  }

  if (loading) return  <div>Loading</div>;
  if (!admin) return <div>Not authorized</div>;

  return (
    <div>
      <h1>User Management</h1>
      <div>
        <input search />
        <button>Search</button>
      <div>
        label:Per Page
        <select>
        </select>
      </div>
    </div>
  )
  );
  );Correct
}
'''

sys.stdout.write(content)