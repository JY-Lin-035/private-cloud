import { useState, useMemo } from 'react';
import { authApi } from '../../api/authApi';



interface RegisterProps {
  onFlip: () => void;
  onNotice: (res: string | string[], cn: string) => void;
}

function Register({ onFlip, onNotice }: RegisterProps) {
  const [userName, setUserName] = useState('');
  const [email, setEmail] = useState('');
  const [PW, setPW] = useState('');
  const [CPW, setCPW] = useState('');
  const [lock, setLock] = useState(true);

  const valUserName = useMemo(() => /^[A-Za-z0-9]{5,100}$/.test(userName), [userName]);

  const valEmail = useMemo(() =>
    /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/.test(email),
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

  const clearInput = () => {
    setEmail('');
    setUserName('');
    setPW('');
    setCPW('');
  };

  async function register() {
    setLock(false);
    try {
      const data = {
        username: userName,
        email: email,
        password: PW,
      };

      const r = await authApi.register(data);
      if (r.message === "success") {
        onNotice(['請驗證電子信箱地址以完成註冊!'], 'text-white');
        clearInput();
        onFlip();
      } else {
        onNotice(['註冊失敗，請稍後再試。'], 'text-red-500');
      }
    } catch (e: any) {
      onNotice([e.message], 'text-red-500');
    }

    setLock(true);
  }

  return (
    <div className="absolute w-full h-full bg-white rounded-xl shadow-md flex flex-col items-center justify-center gap-4 p-6 [backface-visibility:hidden] [transform:rotateY(180deg)_translateZ(250px)]">
      <h2 className="text-xl font-bold">註冊</h2>
      <input
        type="text"
        placeholder="使用者名稱"
        value={userName}
        onChange={(e) => setUserName(e.target.value)}
        className={`w-full px-3 py-2 border rounded ${valUserName || !userName ? '' : 'border-red-500'}`}
      />
      {!valUserName && userName !== '' && (
        <p className="text-red-500 text-[12px]">
          *僅接受英數<br />*長度為 5 到 100 字元之間
        </p>
      )}

      <input
        type="email"
        placeholder="電子信箱"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className={`w-full px-3 py-2 border rounded ${valEmail || !email ? '' : 'border-red-500'}`}
      />
      {!valEmail && email !== '' && (
        <p className="text-red-500 text-[12px]">
          *請輸入正確的 Email 格式
        </p>
      )}

      <input
        type="password"
        placeholder="密碼"
        value={PW}
        onChange={(e) => setPW(e.target.value)}
        className={`w-full px-3 py-2 border rounded ${valPW || !PW ? '' : 'border-red-500'}`}
      />
      {!valPW && PW !== '' && (
        <p className="text-red-500 text-[12px]">
          *密碼須包含英文大小寫、數字以及至少 3 種不同符號<br />*長度為 12 到 100
          字元之間
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
        <p className="text-red-500 text-[12px]">與密碼不相符</p>
      )}

      <button
        onClick={register}
        className="w-full px-4 py-2 text-white bg-green-500 rounded"
        disabled={!(valUserName && valEmail && valPW && valCPW && lock)}
      >
        註冊
      </button>
      <button onClick={onFlip} className="mt-2 text-blue-500" disabled={!lock}>
        返回登入
      </button>
    </div>
  );
}

export default Register;
