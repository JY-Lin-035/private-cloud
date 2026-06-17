import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { useCollab } from '../../hooks/useCollab';
import { authApi } from '../../api/authApi';
import { Users, Wifi, WifiOff, Save } from 'lucide-react';

function CollabEditor({ layoutClass = '' }: { layoutClass?: string }) {
  const { fileUuid } = useParams<{ fileUuid: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<{ id: number; name: string }>({ id: 0, name: '' });
  const [editorContent, setEditorContent] = useState<string>('');
  const [isEditorReady, setIsEditorReady] = useState(false);
  const saveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { content, users, isConnected, sendUpdate, sendCursor, sendSave } = useCollab(
    fileUuid || '',
    user
  );

  useEffect(() => {
    authApi.checkSession().then(s => {
      if (s.authenticated) {
        setUser({ id: s.id, name: s.username || '' });
      } else {
        navigate('/login');
      }
    });
  }, [navigate]);

  // Sync content from WebSocket to editor
  useEffect(() => {
    if (isEditorReady && content !== undefined) {
      setEditorContent(content);
    }
  }, [content, isEditorReady]);

  // Auto-save every 30 seconds
  useEffect(() => {
    if (!isConnected) return;
    saveTimerRef.current = setInterval(() => {
      if (editorContent !== undefined) {
        sendSave(editorContent);
      }
    }, 30000);
    return () => {
      if (saveTimerRef.current) {
        clearInterval(saveTimerRef.current);
      }
    };
  }, [isConnected, editorContent, sendSave]);

  const handleEditorChange = useCallback((value: string | undefined) => {
    if (value !== undefined) {
      setEditorContent(value);
      sendUpdate(value);
    }
  }, [sendUpdate]);

  const handleCursorChange = useCallback((e: any) => {
    if (e?.position) {
      sendCursor({
        lineNumber: e.position.lineNumber,
        column: e.position.column
      });
    }
  }, [sendCursor]);

  const handleSave = useCallback(() => {
    if (editorContent !== undefined) {
      sendSave(editorContent);
    }
  }, [editorContent, sendSave]);

  if (!fileUuid) {
    return <div className="text-white p-8">無效的檔案</div>;
  }

  return (
    <div className={`flex flex-col h-full ${layoutClass}`}>
      {/* Toolbar */}
      <div className="flex items-center justify-between bg-gray-800 px-4 py-2 border-b border-gray-700">
        <div className="flex items-center gap-4">
          <h1 className="text-white text-lg font-semibold">即時共編</h1>
          <div className="flex items-center gap-1 text-sm">
            {isConnected ? (
              <>
                <Wifi className="w-4 h-4 text-green-400" />
                <span className="text-green-400">已連線</span>
              </>
            ) : (
              <>
                <WifiOff className="w-4 h-4 text-red-400" />
                <span className="text-red-400">未連線</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Online users */}
          <div className="flex items-center gap-1 text-sm text-gray-300">
            <Users className="w-4 h-4" />
            <span>{users.length} 人在線</span>
          </div>

          {/* Save button */}
          <button
            onClick={handleSave}
            className="flex items-center gap-1 px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors cursor-pointer text-sm"
          >
            <Save className="w-4 h-4" />
            儲存
          </button>
        </div>
      </div>

      {/* Editor */}
      <div className="flex-1 min-h-0">
        <Editor
          height="100%"
          defaultLanguage="plaintext"
          theme="vs-dark"
          value={editorContent}
          onChange={handleEditorChange}
          onMount={() => setIsEditorReady(true)}
          options={{
            fontSize: 14,
            minimap: { enabled: false },
            automaticLayout: true,
            wordWrap: 'on',
          }}
        />
      </div>
    </div>
  );
}

export default CollabEditor;