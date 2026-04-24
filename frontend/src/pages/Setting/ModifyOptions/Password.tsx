import { useState, useMemo } from 'react';
import Notices from '../../../components/Notices';
import { accountApi } from '../../../api/accountApi';



function Password() {
  const [_lock, setLock] = useState(true);
  const [showMode, setShowMode] = useState(false);
  const [className, setClassName] = useState('');
  const [response, setResponse] = useState<string | string[]>([]);
  const [nowPW, setNowPW] = useState('');
  const [newPW, setNewPW] = useState('');
  const [cNewPW, setCNewPW] = useState('');

  const valNewPW = useMemo(() => {
    const value = newPW;
    const upper = /[A-Z]/.test(value);
    const lower = /[a-z]/.test(value);
    const digit = /\d/.test(value);
    const symbol = value.match(/[^A-Za-z0-9]/g) || [];
    const symbols = new Set(symbol).size >= 3;
    const long = value.length >= 12 && value.length <= 100;

    return upper && lower && digit && symbols && long;
  }, [newPW]);

  const valCNewPW = useMemo(() => newPW === cNewPW, [newPW, cNewPW]);

  async function modifyPW() {
    setLock(false);

    if (nowPW === '' || newPW === '' || cNewPW === '') {
      setClassName('text-red-500');
      setResponse(['密碼不能為空!']);
      setShowMode(true);
      setLock(true);
      return;
    }

    try {
      const data = {
        now_pw: nowPW,
        new_pw: newPW,
      };

      const r = await accountApi.modifyPW(data);
      setClassName('text-white');
      setResponse([r.message]);
      setNowPW('');
      setNewPW('');
      setCNewPW('');
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
          修改密碼
        </time>

        <input
          type="password"
          placeholder="目前密碼"
          value={nowPW}
          onChange={(e) => setNowPW(e.target.value)}
          className="w-full px-3 py-2 mt-6 mb-3 border rounded"
        />

        <input
          type="password"
          placeholder="新密碼"
          value={newPW}
          onChange={(e) => setNewPW(e.target.value)}
          className={`w-full px-3 py-2 mb-3 border rounded ${valNewPW || !newPW ? '' : 'border-red-500'}`}
        />
        {!valNewPW && newPW !== '' && (
          <p className="text-red-500 text-[12px] mb-4">
            *密碼須包含英文大小寫、數字以及至少 3 種不同符號<br />*長度為 12 到 100
            字元之間
          </p>
        )}

        <input
          type="password"
          placeholder="確認新密碼"
          value={cNewPW}
          onChange={(e) => setCNewPW(e.target.value)}
          className={`w-full px-3 py-2 mb-2 border rounded ${valCNewPW ? '' : 'border-red-500'}`}
        />

        <div className="flex justify-between">
          {valCNewPW ? <p></p> : (
            <p className="text-red-500 text-[12px]">
              與密碼不相符
            </p>
          )}

          <button
            type="button"
            onClick={modifyPW}
            className="text-white bg-gradient-to-br from-green-400 to-blue-600 hover:bg-gradient-to-bl font-medium rounded-lg text-sm px-5 py-2.5 text-center me-2 mb-2"
            disabled={!nowPW || !newPW || !valCNewPW}
          >
            確認修改
          </button>
        </div>
      </li>
    </>
  );
}

export default Password;
