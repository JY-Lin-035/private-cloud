import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { useCollab } from '../../hooks/useCollab';
import { authApi } from '../../api/authApi';
import { Users, Wifi, WifiOff, Save, Clock, LogOut } from 'lucide-react';

function CollabEditor({ layoutClass = '' }: { layoutClass?: string }) {
  const { fileUuid } = useParams<{ fileUuid: string }>();
  const navigate = useNavigate();
  const [user, setUser] = useState<{ id: number; name: string }>({ id: 0, name: '' });
  const [editorContent, setEditorContent] = useState<string>('');
  const [isEditorReady, setIsEditorReady] = useState(false);
  const saveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { content, users, snapshots, isConnected, sendUpdate, sendCursor, sendSave, switchVersion } = useCollab(
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
      <div className="flex flex-wrap items-center justify-between bg-gray-800 px-2 sm:px-4 py-2 border-b border-gray-700 gap-2">
        <div className="flex items-center gap-2 sm:gap-4">
          <button
            onClick={() => navigate('/collaboration')}
            className="flex items-center gap-1 px-2 py-1 bg-gray-700 text-white rounded hover:bg-gray-600 transition-colors cursor-pointer text-xs sm:text-sm"
            title="退出共編"
          >
            <LogOut className="w-3 h-3 sm:w-4 sm:h-4" />
            <span className="hidden sm:inline">退出</span>
          </button>
          <h1 className="text-white text-sm sm:text-lg font-semibold">即時共編</h1>
          <div className="flex items-center gap-1 text-xs sm:text-sm">
            {isConnected ? (
              <>
                <Wifi className="w-3 h-3 text-green-400" />
                <span className="text-green-400">已連線</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3 h-3 text-red-400" />
                <span className="text-red-400">未連線</span>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1 sm:gap-4 flex-wrap justify-center">
          <div className="flex items-center gap-1 text-xs sm:text-sm text-gray-300">
            <Users className="w-3 h-3 sm:w-4 sm:h-4" />
            <span>{users.length}</span>
          </div>

          <div className="flex items-center gap-1 text-xs sm:text-sm">
            <Clock className="w-3 h-3 sm:w-4 sm:h-4 text-gray-400" />
            {snapshots.length > 0 ? (
              <select
                onChange={(e) => switchVersion(Number(e.target.value))}
                className="bg-gray-700 text-white text-xs sm:text-sm rounded px-1 py-0.5 sm:px-2 sm:py-1 border border-gray-600 cursor-pointer max-w-[80px] sm:max-w-none"
              >
                <option value="">版本</option>
                {snapshots.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.timestamp}
                  </option>
                ))}
              </select>
            ) : (
              <span className="text-gray-500 text-xs">無</span>
            )}
          </div>

          <button
            onClick={handleSave}
            className="flex items-center gap-1 px-2 py-0.5 sm:px-3 sm:py-1 bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors cursor-pointer text-xs text-sm"
          >
            <Save className="w-3 h-3 sm:w-4 sm:h-4" />
            <span className="hidden sm:inline">儲存</span>
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