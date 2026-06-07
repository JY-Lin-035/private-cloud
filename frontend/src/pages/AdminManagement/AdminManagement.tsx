import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { adminApi } from '../../api/adminApi';
import { authApi } from '../../api/authApi';

function AdminPage() {
  const nav = useNavigate();
  const [loading, setLoading] = useState(true);
  const [admin, setAdmin] = useState(false);
  const [users, setUsers] = useState([]);
  const [total, setTotal] = useState(0);
  const [totalPages, setTotalPages] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(10);
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

  async function loadUsers() {
    try {
      const data = await adminApi.getUsers(page, perPage, search);
      setUsers(data.users);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch (e) {
      console.error(e);
    }
  }

  useEffect(() => {
    if (admin) loadUsers();
  }, [page, perPage, admin]);

  async function handleSearch() {
    const input = document.getElementById('search-inp');
    if (input) setSearch(input.value.trim());
    setPage(1);
  }

  if (loading) {
    return (<div className='p-4 text-gray-400'>Verifying...</div>);
  }
  if (!admin) return null;

  return (
    <div className='p-6'>
      <h1 className='text-white text-2xl font-bold mb-4'>Admin</h1>
    </div>
  );
}

export default AdminPage;