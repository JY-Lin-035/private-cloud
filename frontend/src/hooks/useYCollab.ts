import { useCallback, useEffect, useRef, useState } from 'react';
import * as Y from 'yjs';

interface Snapshot {
  id: string | number;
  timestamp: string;
}

interface UseYCollabReturn {
  users: number[];
  snapshots: Snapshot[];
  isConnected: boolean;
  persistText: (content: string, createSnapshot?: boolean) => void;
  switchVersion: (versionId: string) => void;
}

const remoteOrigin = Symbol('remote');
const initOrigin = Symbol('init');

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return window.btoa(binary);
}

function base64ToBytes(base64: string): Uint8Array {
  const binary = window.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

function replaceText(ytext: Y.Text, content: string, origin: symbol): void {
  const length = ytext.length;
  ytext.doc?.transact(() => {
    if (length > 0) {
      ytext.delete(0, length);
    }
    if (content) {
      ytext.insert(0, content);
    }
  }, origin);
}

export function useYCollab(
  fileUuid: string,
  user: { id: number; name: string },
  ydoc: Y.Doc,
  ytext: Y.Text
): UseYCollabReturn {
  const [users, setUsers] = useState<number[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const initializedRef = useRef(false);
  const canSendUpdatesRef = useRef(false);
  const projectionTimerRef = useRef<number | null>(null);

  useEffect(() => {
    if (!fileUuid || !user.id) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//localhost:8000/ws/collab/${fileUuid}?user_id=${user.id}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;
    initializedRef.current = false;
    canSendUpdatesRef.current = false;

    const sendProjection = () => {
      if (ws.readyState === WebSocket.OPEN && initializedRef.current && canSendUpdatesRef.current) {
        ws.send(JSON.stringify({
          type: 'y_projection',
          content: ytext.toString(),
        }));
      }
    };

    const scheduleProjection = () => {
      if (projectionTimerRef.current !== null) {
        window.clearTimeout(projectionTimerRef.current);
      }
      projectionTimerRef.current = window.setTimeout(() => {
        projectionTimerRef.current = null;
        sendProjection();
      }, 250);
    };

    const handleUpdate = (update: Uint8Array, origin: unknown) => {
      if (origin !== initOrigin) {
        scheduleProjection();
      }
      if (origin === remoteOrigin || origin === initOrigin) return;
      if (ws.readyState === WebSocket.OPEN && initializedRef.current && canSendUpdatesRef.current) {
        ws.send(JSON.stringify({
          type: 'y_update',
          update: bytesToBase64(update),
        }));
      }
    };

    ydoc.on('update', handleUpdate);

    ws.onopen = () => {
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case 'load_file':
            if ((data.y_updates || []).length > 0) {
              (data.y_updates || []).forEach((update: string) => {
                Y.applyUpdate(ydoc, base64ToBytes(update), remoteOrigin);
              });
              initializedRef.current = true;
              canSendUpdatesRef.current = true;
            } else if (data.needs_y_init) {
              replaceText(ytext, data.content || '', initOrigin);
              ws.send(JSON.stringify({
                type: 'y_init_state',
                update: bytesToBase64(Y.encodeStateAsUpdate(ydoc)),
                content: ytext.toString(),
              }));
              initializedRef.current = true;
              canSendUpdatesRef.current = true;
            } else {
              replaceText(ytext, data.content || '', initOrigin);
              initializedRef.current = true;
              canSendUpdatesRef.current = false;
            }
            setUsers(data.users || []);
            setSnapshots(data.snapshots || []);
            break;
          case 'y_init_state':
            if (!canSendUpdatesRef.current) {
              replaceText(ytext, '', remoteOrigin);
              Y.applyUpdate(ydoc, base64ToBytes(data.update), remoteOrigin);
              initializedRef.current = true;
              canSendUpdatesRef.current = true;
            }
            break;
          case 'y_update':
            Y.applyUpdate(ydoc, base64ToBytes(data.update), remoteOrigin);
            break;
          case 'y_reset':
          case 'load_version':
            canSendUpdatesRef.current = false;
            replaceText(ytext, data.content || '', remoteOrigin);
            ws.send(JSON.stringify({
              type: 'y_init_state',
              update: bytesToBase64(Y.encodeStateAsUpdate(ydoc)),
              content: ytext.toString(),
              reset: true,
            }));
            canSendUpdatesRef.current = true;
            setSnapshots(data.snapshots || []);
            break;
          case 'apply_version':
            replaceText(ytext, data.content || '', Symbol('apply-version'));
            setSnapshots(data.snapshots || []);
            break;
          case 'snapshots':
            setSnapshots(data.snapshots || []);
            break;
          case 'users':
            setUsers(data.users || []);
            break;
          case 'switch_version_failed':
            console.error('Switch version failed:', data.message, data.version_id);
            break;
          case 'user_joined':
            setUsers((prev) => [...new Set([...prev, data.user_id])]);
            break;
          case 'user_left':
            setUsers((prev) => prev.filter((id) => id !== data.user_id));
            break;
        }
      } catch (e) {
        console.error('WebSocket message error:', e);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      initializedRef.current = false;
    };

    ws.onerror = (e) => {
      console.error('WebSocket error:', e);
      setIsConnected(false);
    };

    return () => {
      if (projectionTimerRef.current !== null) {
        window.clearTimeout(projectionTimerRef.current);
        projectionTimerRef.current = null;
      }
      ydoc.off('update', handleUpdate);
      ws.close();
    };
  }, [fileUuid, user.id, ydoc, ytext]);

  useEffect(() => {
    if (!isConnected) return;

    const timer = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: 'get_snapshots' }));
      }
    }, 5000);

    return () => clearInterval(timer);
  }, [isConnected]);

  const persistText = useCallback((content: string, createSnapshot = false) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'persist_text',
        content,
        create_snapshot: createSnapshot,
      }));
    }
  }, []);

  const switchVersion = useCallback((versionId: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'switch_version',
        version_id: versionId,
      }));
    }
  }, []);

  return { users, snapshots, isConnected, persistText, switchVersion };
}
