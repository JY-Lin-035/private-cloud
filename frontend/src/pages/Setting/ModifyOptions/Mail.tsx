import { useState, useMemo, useEffect } from 'react';
import Notices from '../../../components/Notices';
import { accountApi } from '../../../api/accountApi';



function Mail() {
  const [_lock, setLock] = useState(true);
  const [showMode, setShowMode] = useState(false);
  const [className, setClassName] = useState('');
  const [response, setResponse] = useState<string | string[]>([]);
  const [nowEmail, setNowEmail] = useState('');
  const [checkNowEmail, setCheckNowEmail] = useState('');
  const [newEmail, setNewEmail] = useState('');
  const [code, setCode] = useState('');
  const [valCode, _setValCode] = useState(true);
  const [waitCode, setWaitCode] = useState(false);
  const [waitTime, setWaitTime] = useState(30);

  useEffect(() => {
    setNowEmail(localStorage.getItem('email') || '');
  }, []);

  const valEmail1 = useMemo(() =>
    /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(checkNowEmail),
    [checkNowEmail]
  );

  const valEmail2 = useMemo(() =>
    /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(newEmail),
    [newEmail]
  );

  async function getCode() {
    setLock(false);

    if (newEmail === '') {
      setClassName('text-red-500');
      setResponse(['電子信箱不能為空!']);
      setShowMode(true);
      setLock(true);
      return;
    }

    try {
      const data = {
        mode: 'mail',
        email: newEmail,
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

  async function modifyMail() {
    setLock(false);

    if (checkNowEmail === '' || newEmail === '' || code === '') {
      setClassName('text-red-500');
      setResponse(['電子信箱或驗證碼不能為空!']);
      setShowMode(true);
      setLock(true);
      return;
    }

    try {
      const data = {
        email: newEmail,
        check_email: checkNowEmail,
        code: code,
      };

      const r = await accountApi.modifyMail(data);
      setNowEmail(r.email);
      localStorage.setItem('email', r.email);
      setClassName('text-white');
      setResponse(['修改成功!']);
      setCheckNowEmail('');
      setNewEmail('');
      setCode('');
      setShowMode(true);
    } catch (e: any) {
      setResponse([e.message]);
      setClassName('text-red-500');
      setShowMode(true);
    }
    setLock(true);
  }

  return (
    <>
      <Notices
        notices={response}
        showMode={showMode}
        className={className}
        onClose={() => { setShowMode(false); setLock(true); }}
      />
      <li className="mb-10 ms-4">
        <div className="absolute w-3 h-3 bg-gray-700 rounded-full mt-1.5 -start-1.5 border border-white"></div>
        <time className="mb-1 text-[3rem] font-normal leading-none text-[#1d92ff]">
          修改信箱地址
        </time>

        <h3 className="text-sm mt-6 tracking-widest font-semibold text-[red]">
          目前電子信箱地址: {nowEmail}
        </h3>

        <input
          type="email"
          placeholder="驗證目前電子信箱"
          value={checkNowEmail}
          onChange={(e) => setCheckNowEmail(e.target.value)}
          className={`w-[70%] px-3 py-2 bg-white rounded mt-[10px] mr-3 ${valEmail1 || !checkNowEmail ? '' : 'border-red-500'}`}
        />

        {!valEmail1 && checkNowEmail !== '' && (
          <p className="text-red-500 text-[12px]">
            *請輸入正確的 Email 格式
          </p>
        )}

        <div>
          <input
            type="email"
            placeholder="電子信箱"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            className={`w-[70%] px-3 py-2 bg-white rounded mt-[10px] mr-3 ${valEmail2 || !newEmail ? '' : 'border-red-500'}`}
          />

          <button
            type="button"
            onClick={getCode}
            className="text-white bg-gradient-to-br from-green-400 to-blue-600 hover:bg-gradient-to-bl font-medium rounded-lg text-sm px-5 py-2.5 text-center me-2 mb-2"
            disabled={!valEmail2 || waitCode}
          >
            {waitCode ? `傳送驗證碼(${waitTime})` : '傳送驗證碼'}
          </button>
        </div>
        {!valEmail2 && newEmail !== '' && (
          <p className="text-red-500 text-[12px]">
            *請輸入正確的 Email 格式
          </p>
        )}

        <span>
          <input
            type="text"
            placeholder="輸入驗證碼"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className={`px-3 py-2 mt-4 mr-3 bg-white rounded ${valCode ? '' : 'border-red-500'}`}
          />

          <button
            type="button"
            onClick={modifyMail}
            className="text-white bg-gradient-to-br from-green-400 to-blue-600 hover:bg-gradient-to-bl font-medium rounded-lg text-sm px-5 py-2.5 text-center me-2 mb-2"
            disabled={!code || !newEmail}
          >
            確認修改
          </button>
        </span>

        {!valCode && (
          <p className="text-red-500 text-[12px]">驗證碼錯誤</p>
        )}
      </li>
    </>
  );
}

export default Mail;
