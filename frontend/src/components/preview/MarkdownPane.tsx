import { useMemo, useState } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import EditorPane from './EditorPane';

interface Props {
  filename: string;
  value: string;
  onChange: (v: string) => void;
  onSave?: () => void;
}

function sanitize(html: string): string {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['style', 'script', 'iframe', 'object', 'embed', 'form', 'input', 'link', 'meta', 'base'],
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover', 'formaction', 'srcset'],
    ALLOW_DATA_ATTR: false,
  });
}

/** Markdown preview + inline source editing toggle. */
function MarkdownPane({ filename, value, onChange, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const html = useMemo(() => {
    try {
      return sanitize(marked.parse(value, { async: false }) as string);
    } catch {
      return '<p>渲染失敗，請切換到編輯</p>';
    }
  }, [value]);

  return (
    <div className="h-full flex flex-col">
      <div className="flex gap-2 p-2 border-b border-gray-700">
        <button type="button" onClick={() => setEditing(false)}
          className={`px-3 py-1 rounded text-sm ${!editing ? 'bg-blue-600 text-white' : 'bg-gray-700'}`}>預覽</button>
        <button type="button" onClick={() => setEditing(true)}
          className={`px-3 py-1 rounded text-sm ${editing ? 'bg-blue-600 text-white' : 'bg-gray-700'}`}>編輯原始碼</button>
      </div>
      <div className="flex-1 overflow-auto min-h-[60vh]">
        {editing ? (
          <EditorPane filename={filename} value={value} onChange={onChange} onSave={onSave} />
        ) : (
          <article className="md-preview max-w-none p-4 break-words text-gray-100"
            dangerouslySetInnerHTML={{ __html: html }} />
        )}
      </div>
    </div>
  );
}

export default MarkdownPane;
