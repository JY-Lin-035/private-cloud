import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Base64 } from 'js-base64';
import Login from './Login';
import Register from './Register';
import Notices from '../../components/Notices';
import { authApi } from '../../api/authApi';

function LoginRegisterPage({ layoutClass = "" }: { layoutClass?: string }) {
  const navigate = useNavigate();
  const [flipped, setFlipped] = useState(false);
  const [showMode, setShowMode] = useState(false);
  const [response, setResponse] = useState<string | string[]>('');
  const [className, setClassName] = useState('');
  const [IN, setIN] = useState(false);

  const checkSession = async () => {
    try {
      await authApi.checkSession();
      const PATH = localStorage.getItem('previousPath');
      if (!PATH) {
        navigate(`/fileList/${Base64.encodeURI('Home')}`);
      } else {
        navigate(PATH);
      }
    } catch (e) {
      localStorage.clear();
      localStorage.setItem('previousPath', '/');
    }
  };

  useEffect(() => {
    checkSession();
    setTimeout(() => {
      setIN(true);
    }, 1);
  }, [navigate]);

  const handleNotice = (res: string | string[], cn: string) => {
    setClassName(cn);
    setResponse(res);
    setShowMode(true);
  };

  const handleClose = () => {
    setShowMode(false);
  };

  return (
    <div className={`flex items-center justify-center ${layoutClass}`}>
      <Notices
        inputShow={false}
        folderName=""
        notices={response}
        showMode={showMode}
        className={className}
        onClose={handleClose}
      />

      <div
        className={`w-[20vw] max-w-[370px] min-w-[250px] transition-all duration-[800ms] ease-in-out [perspective:10000px] ${flipped ? 'h-[570px]' : 'h-[420px]'
          } ${IN ? 'opacity-100' : 'opacity-0'}`}
      >
        <div
          className={`w-full h-full transition-transform duration-[800ms] [transform-style:preserve-3d] ${flipped ? '[transform:rotateY(-180deg)]' : ''
            }`}
        >
          <Login
            onFlip={() => setFlipped(true)}
            onNotice={handleNotice}
          />

          <Register
            onFlip={() => setFlipped(false)}
            onNotice={handleNotice}
          />
        </div>
      </div>
    </div>
  );
}

export default LoginRegisterPage;
