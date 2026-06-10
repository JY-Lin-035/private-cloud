import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import Drawer from './Drawer';
import { authApi } from '../api/authApi';

import logoImage from '../assets/Logo.png';

function Nav({ layoutClass = '' }: { layoutClass?: string }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [loggedIn, setLoggedIn] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await authApi.checkSession();
        setLoggedIn(data.authenticated === true);
      } catch {
        setLoggedIn(false);
      }
      setLoading(false);
    })();
  }, [location.pathname]);

  const isPublic =
    location.pathname === '/' ||
    location.pathname === '/forget-password' ||
    location.pathname.startsWith('/share/');

  const isLoginPage = location.pathname === '/login';

  function handleLogoClick() {
    navigate('/');
  }

  return (
    <nav className={'border-gray-200 bg-gray-800 ' + layoutClass}>
      <div className='flex flex-wrap items-center justify-between w-full mx-auto py-[1rem] px-[2rem]'>
        <a href='#' onClick={handleLogoClick} className='flex items-center space-x-3'>
                  <img src={logoImage} className='w-auto h-10 sm:h-14 md:h-16' alt='Logo' />
                  <h2 className='self-center text-xl sm:text-2xl md:text-[2rem] font-semibold whitespace-nowrap text-white'>Meow</h2>
                </a>
        {!isPublic && !isLoginPage && <Drawer />}
                {isLoginPage && !loading && (
                  <button onClick={() => navigate('/')} className='px-3 py-2 bg-gradient-to-r from-blue-400 to-cyan-400 text-white rounded-md cursor-pointer'>
                    Home
                  </button>
                )}
                {isPublic && !loggedIn && !loading && (
                  <button onClick={() => navigate('/login')} className='px-3 py-2 bg-gradient-to-r from-blue-400 to-cyan-400 text-white rounded-md cursor-pointer'>
                    Login
                  </button>
                )}
                {(isPublic && loggedIn && !loading) && <Drawer />}
      </div>
    </nav>
  );
}
  
export default Nav;