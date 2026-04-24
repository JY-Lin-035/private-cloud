import { useLocation, useNavigate } from 'react-router-dom';
import { Base64 } from 'js-base64';
import Drawer from './Drawer';

import logoImage from '../assets/J.png';



function Nav({ layoutClass = "" }: { layoutClass?: string }) {
  const location = useLocation();
  const navigate = useNavigate();

  const shouldShowDrawer =
    location.pathname !== '/' &&
    location.pathname !== '/forgetPassword' &&
    !location.pathname.startsWith('/share/');

  function handleLogoClick() {
    if (location.pathname === '/' || location.pathname === '/forgetPassword') {
      navigate('/');
    } else {
      navigate(`/fileList/${Base64.encodeURI('Home')}`);
    }
  }

  return (
    <nav className={`border-gray-200 bg-gray-800 ${layoutClass}`}>
      <div className="flex flex-wrap items-center justify-between w-full mx-auto py-[1rem] px-[2rem]">
        <a href="#" onClick={handleLogoClick} className="flex items-center space-x-3 rtl:space-x-reverse">
          <img src={logoImage} className="w-auto h-16" alt="Logo" />
          <span className="self-center text-[2rem] font-semibold whitespace-nowrap text-white">
            Meow
          </span>
        </a>

        {shouldShowDrawer && <Drawer />}
      </div>
    </nav>
  );
}

export default Nav;