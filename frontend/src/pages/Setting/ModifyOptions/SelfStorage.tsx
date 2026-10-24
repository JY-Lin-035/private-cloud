import { useState, useEffect, useMemo } from 'react';
import Notices from '../../../components/Notices';
import { adminApi } from '../../../api/adminApi';
import { useStorage } from '../../../store/storage';



function SelfStorage() {
  const [lock, setLock] = useState(true);
  const [showMode, setShowMode] = useState(false);
  const [className, setClassName] = useState('');
  const [response, setResponse] = useState<string | string[]>([]);
  const [input, setInput] = useState('');
  const [unit, setUnit] = useState('GB');
  const getFromAPI = useStorage(s => s.getFromAPI);
  const format = useStorage(s => s.format);
  const usedStorage = useStorage(s => s.usedStorage);
  const totalStorage = useStorage(s => s.totalStorage);

  useEffect(() => {
    getFromAPI();
  }, []);

  const newSize = useMemo(() => {
    const n = Number(input);
    if (!input || Number.isNaN(n) || n < 0) return null;
    const factor: Record<string, number> = { B: 1, KB: 1024, MB: 1024 ** 2, GB: 1024 ** 3, TB: 1024 ** 4 };
    return Math.round(n * factor[unit]);
  }, [input, unit]);

  async function save() {
    if (newSize === null) {
      setClassName('text-red-500');
      setResponse(['請輸入有效的容量數值!']);
      setShowMode(true);
      return;
    }
    setLock(false);
    try {
      await adminApi.updateOwnQuota(newSize);
      await getFromAPI();
      setInput('');
      setClassName('text-white');
      setResponse(['可用空間已更新!']);
    } catch (e: any) {
      setClassName('text-red-500');
      setResponse([e?.message ?? '更新失敗，請稍後再試']);
    }
    setShowMode(true);
    setLock(true);
  }

  return (
    <li className="mb-10 ms-4">
      <Notices
        inputShow={false}
        folderName=""
        notices={response}
        showMode={showMode}
        className={className}
        onClose={() => setShowMode(false)}
      />
      <div className="absolute w-3 h-3 bg-gray-700 rounded-full mt-1.5 -start-1.5 border border-white"></div>
      <time className="mb-1 text-[3rem] font-normal leading-none text-[#1d92ff]">
        可用空間
      </time>

      <p className="text-white text-sm mb-2">
        已使用 {format(usedStorage)[0]} {format(usedStorage)[1]} / 上限 {format(totalStorage)[0]} {format(totalStorage)[1]}
      </p>

      <div className="flex gap-2 mb-2">
        <input
          type="number"
          min="0"
          placeholder="新上限"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          className="flex-1 px-3 py-2 text-black border rounded"
        />
        <select
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          className="px-2 py-2 text-black border rounded bg-white"
        >
          <option>B</option>
          <option>KB</option>
          <option>MB</option>
          <option>GB</option>
          <option>TB</option>
        </select>
      </div>

      <button
        type="button"
        onClick={save}
        disabled={!lock || newSize === null}
        className={`text-white bg-gradient-to-r from-cyan-500 to-blue-500 hover:bg-gradient-to-bl font-medium rounded-lg text-sm px-5 py-2.5 text-center me-2 mb-2 ${!lock || newSize === null ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
      >
        儲存
      </button>
    </li>
  );
}

export default SelfStorage;
