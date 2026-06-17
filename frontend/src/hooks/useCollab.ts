import { useState, useEffect, useRef, useCallback } from 'react';

interface CursorPosition {
  lineNumber: number;
  column: number;
}

interface Snapshot {
  id: number;
  timestamp: string;
}

interface UseCollabReturn {
  content: string;
  users: number[];
  snapshots: Snapshot[];
  isConnected: boolean;
  sendUpdate: (content: string) => void;
  sendCursor: (cursor: CursorPosition) => void;
  sendSave: (content: string) => void;
  switchVersion: (versionId: number) => void;
}

export function useCollab(fileUuid: string, user: { id: number; name: string }): UseCollabReturn {
  const [content, setContent] = useState<string>('');
  const [users, setUsers] = useState<number[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!fileUuid || !user.id) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//localhost:8000/ws/collab/${fileUuid}?user_id=${user.id}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case 'load_file':
            setContent(data.content || '');
            setUsers(data.users || []);
            break;
          case 'update':
            setContent(data.content || '');
            break;
          case 'user_joined':
            setUsers(prev => [...new Set([...prev, data.user_id])]);
            break;
          case 'user_left':
            setUsers(prev => prev.filter(id => id !== data.user_id));
            break;
        }
      } catch (e) {
        console.error('WebSocket message error:', e);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
    };

    ws.onerror = (e) => {
      console.error('WebSocket error:', e);
      setIsConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [fileUuid, user.id]);

  const sendUpdate = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'update',
        content
      }));
    }
  }, []);

  const sendCursor = useCallback((cursor: CursorPosition) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'cursor',
        cursor
      }));
    }
  }, []);

  const switchVersion = useCallback((versionId: number) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'switch_version',
        version_id: versionId
      }));
    }
  }, []);

  const sendSave = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'save',
        content
      }));
    }
  }, []);

  return { content, users, snapshots, isConnected, sendUpdate, sendCursor, sendSave, switchVersion };
}