import { useState } from 'react';
import EditorPane from './EditorPane';

interface Props {
  filename: string;
  value: string;
  onChange: (v: string) => void;
  onSave?: () => void;
}

/** JSON editor with format/validation. */
function JsonPane({ filename, value, onChange, onSave }: Props) {
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  function format() {
    try {
      const parsed = JSON.parse(value);
      onChange(JSON.stringify(parsed, null, 2));
      setMsg({ ok: true, text: '已格式化，JSON 有效' });
    } catch (e) {
      setMsg({ ok: false, text: `JSON 錯誤：${(e as Error).message}` });
    }
  }

  function validate() {
    try {
      JSON.parse(value);
      setMsg({ ok: true, text: 'JSON 有效' });
    } catch (e) {
      setMsg({ ok: false, text: `JSON 錯誤：${(e as Error).message}` });
    }
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex items-center gap-2 p-2 border-b border-gray-700">
        <button type="button" onClick={validate} className="px-3 py-1 rounded text-sm bg-gray-700 hover:bg-gray-600 text-gray-100">驗證</button>
        <button type="button" onClick={format} className="px-3 py-1 rounded text-sm bg-gray-700 hover:bg-gray-600 text-gray-100">格式化</button>
        {msg && <span className={`text-sm ${msg.ok ? 'text-green-400' : 'text-red-400'}`}>{msg.text}</span>}
      </div>
      <div className="flex-1 min-h-0">
        <EditorPane filename={filename} value={value} onChange={onChange} onSave={onSave} />
      </div>
    </div>
  );
}

export default JsonPane;
