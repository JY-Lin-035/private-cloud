import { useState, useMemo, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Notices from '../../components/Notices';
import { authApi } from '../../api/authApi';
import { accountApi } from '../../api/accountApi';



function ResetPW() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [PW, setPW] = useState('');
  const [CPW, setCPW] = useState('');
  const [code, setCode] = useState('');
  const [valCode, _setValCode] = useState(true);
  const [response, setResponse] = useState<string | string[]>([]);
  const [showMode, setShowMode] = useState(false);
  const [inputShow, setInputShow] = useState(false);
  const [className, setClassName] = useState('');
  const [lock, setLock] = useState(true);
  const [IN, setIN] = useState(false);
  const [waitCode, setWaitCode] = useState(false);
  const [waitTime, setWaitTime] = useState(30);

  async function checkSession() {
    try {
      await authApi.checkSession();
      const PATH = localStorage.getItem('previousPath');
      if (!PATH) {
        navigate('/fileList');
      } else {
        navigate(PATH);
      }
    } catch (e) {
      localStorage.clear();
      localStorage.setItem('previousPath', '/');
    }
  }

  useEffect(() => {
    checkSession();

    setTimeout(() => {
      setIN(true);
    }, 1);
  }, []);

  const clearInput = () => {
    setEmail('');
    setPW('');
    setCPW('');
    setCode('');
    setResponse('');
    setShowMode(false);
    setInputShow(false);
    setClassName('');
    setLock(true);
  };

  const valEmail = useMemo(
    () => /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email),
    [email]
  );

  const valPW = useMemo(() => {
    const value = PW;
    const upper = /[A-Z]/.test(value);
    const lower = /[a-z]/.test(value);
    const digit = /\d/.test(value);
    const symbol = value.match(/[^A-Za-z0-9]/g) || [];
    const symbols = new Set(symbol).size >= 3;
    const long = value.length >= 12 && value.length <= 100;

    return upper && lower && digit && symbols && long;
  }, [PW]);

  const valCPW = useMemo(() => PW === CPW, [PW, CPW]);

  async function getCode() {
    setLock(false);

    if (email === '') {
      setClassName('text-red-500');
      setResponse(['電子信箱不能為空!']);
      setShowMode(true);
      setLock(true);
      return;
    }

    try {
      const data = {
        mode: 'pw',
        email: email,
      };

      setWaitCode(true);
      const timer = setInterval(() => {
        setWaitTime((prev) => {
          if (prev > 0) {
            return prev - 1;
          } else {
            clearInterval(timer);
            setWaitCode(false);
            return 30;
          }
        });
      }, 1000);

      const r = await accountApi.getCode(data);
      setClassName('text-white');
      setResponse([r.message]);
      setShowMode(true);
    } catch (e: any) {
      setResponse(Object.values(e.message).flat() as string[]);
      setClassName('text-red-500');
      setShowMode(true);
    }
    setLock(true);
  }

  async function resetPW() {
    setLock(false);

    if (PW === '' || code === '') {
      setClassName('text-red-500');
      setResponse(['密碼及驗證碼不能為空!']);
      setShowMode(true);
      setLock(true);
      return;
    }

    try {
      const data = {
        email: email,
        password: PW,
        code: code,
      };

      await accountApi.resetPassword(data);
      setShowMode(true);
      back();
    } catch (e: any) {
      setResponse(Object.values(e.message).flat() as string[]);
      setClassName('text-red-500');
      setShowMode(true);
    }
    setLock(true);
  }

  function back() {
    const PATH = localStorage.getItem('previousPath');
    if (!PATH) {
      navigate('/');
    } else {
      navigate(PATH);
    }

    clearInput();
  }

  return (
    <div className="flex items-center justify-center bg-gray-500">
      <Notices
        inputShow={inputShow}
        notices={response}
        showMode={showMode}
        className={className}
        onClose={() => { setShowMode(false); setLock(true); }}
      />

      <div className={`w-[370px] [perspective:10000px] transition-all duration-[800ms] ease-in-out ${IN ? 'opacity-100' : 'opacity-0'}`}>
        <div className="relative flex flex-col items-center justify-center w-full h-full gap-4 p-6 bg-white shadow-md rounded-xl">
          <h2 className="text-xl font-bold">重設密碼</h2>

          <input
            type="email"
            placeholder="電子信箱"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={`w-full px-3 py-2 border rounded mt-[10px] ${(valEmail || !email) ? '' : 'border-red-500'}`}
          />
          {!valEmail && email !== '' && (
            <p className="text-red-500 text-[12px]">
              *請輸入正確的 Email 格式
            </p>
          )}

          <input
            type="password"
            placeholder="新密碼"
            value={PW}
            onChange={(e) => setPW(e.target.value)}
            className={`w-full px-3 py-2 border rounded ${(valPW || !PW) ? '' : 'border-red-500'}`}
          />
          {!valPW && PW !== '' && (
            <p className="text-red-500 text-[12px]">
              *密碼須包含英文大小寫、數字以及至少 3 種不同符號<br />*長度為 12 到 100 字元之間
            </p>
          )}

          <input
            type="password"
            placeholder="確認密碼"
            value={CPW}
            onChange={(e) => setCPW(e.target.value)}
            className={`w-full px-3 py-2 border rounded ${valCPW ? '' : 'border-red-500'}`}
          />
          {!valCPW && CPW !== '' && (
            <p className="text-red-500 text-[12px]">
              與密碼不相符
            </p>
          )}

          <span className="flex justify-between w-full mt-[20px]">
            <input
              type="text"
              placeholder="輸入驗證碼"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className={`px-3 py-2 border rounded ${valCode ? '' : 'border-red-500'}`}
            />

            <button
              onClick={getCode}
              className={`px-4 py-2 text-white rounded ${waitCode ? 'bg-gray-500' : 'bg-blue-500'}`}
              disabled={!(valEmail) || waitCode}
            >
              {waitCode ? `傳送驗證碼(${waitTime})` : '傳送驗證碼'}
            </button>
          </span>

          {!valCode && (
            <p className="text-red-500 text-[12px]">
              驗證碼錯誤
            </p>
          )}

          <button
            onClick={resetPW}
            className="bg-blue-500 text-white px-4 py-2 rounded w-full mt-[25px]"
            disabled={!(PW && lock && code && valEmail)}
          >
            送出
          </button>
          <button onClick={back} className="mt-2 text-blue-500" disabled={!lock}>
            返回
          </button>
        </div>
      </div>
    </div>
  );
}

export default ResetPW;
