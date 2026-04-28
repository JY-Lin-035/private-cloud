import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../../api/authApi';



interface LoginProps {
  onFlip: () => void;
  onNotice: (res: string | string[], cn: string) => void;
}

function Login({ onFlip, onNotice }: LoginProps) {
  const navigate = useNavigate();
  const [userName, setUserName] = useState('');
  const [PW, setPW] = useState('');
  const [lock, setLock] = useState(true);

  async function login() {
    setLock(false);

    if (userName === '' || PW === '') {
      onNotice(['使用者名稱和密碼不能為空!'], 'text-red-500');
      setLock(true);
      return;
    }

    try {
      const data = {
        username: userName,
        password: PW,
      };

      const r = await authApi.login(data);
      console.log(r);
      localStorage.setItem("email", r.email);
      setUserName('');
      setPW('');
      navigate('/file-list');
    } catch (e: any) {
      onNotice([e.message], 'text-red-500');
    }

    setLock(true);
  }

  const goForgetPW = () => navigate('/forget-password');

  return (
    <div className="absolute w-full h-full bg-white rounded-xl shadow-md flex flex-col justify-center items-center gap-4 p-6 [backface-visibility:hidden] [transform:translateZ(250px)]">
      <div className="flex-1"></div>
      <h2 className="text-xl font-bold">登入</h2>
      <input
        type="text"
        placeholder="使用者名稱"
        value={userName}
        onChange={(e) => setUserName(e.target.value)}
        className="border w-full px-3 py-2 rounded mt-[30px]"
      />
      <input
        type="password"
        placeholder="密碼"
        value={PW}
        onChange={(e) => setPW(e.target.value)}
        className="w-full px-3 py-2 border rounded"
      />
      <button
        onClick={login}
        className={`bg-blue-500 text-white px-4 py-2 rounded w-full mt-[30px] ${userName && PW && lock ? 'cursor-pointer' : 'cursor-not-allowed'}`}
        disabled={!(userName && PW && lock)}
      >
        登入
      </button>
      <span className="flex justify-between w-full mt-[30px]">
        <button onClick={goForgetPW} className={`text-blue-500 ${lock ? 'cursor-pointer' : 'cursor-not-allowed'}`} disabled={!lock}>
          忘記密碼?
        </button>
        <button onClick={onFlip} className={`text-blue-500 ${lock ? 'cursor-pointer' : 'cursor-not-allowed'}`} disabled={!lock}>
          註冊
        </button>
      </span>
      <div className="flex-1"></div>
    </div>
  );
}

export default Login;
