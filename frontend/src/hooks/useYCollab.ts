import { useCallback, useEffect, useRef, useState } from 'react';
import * as Y from 'yjs';
import { buildWebSocketUrl } from '../config/api';
import { collaborationApi } from '../api/collaborationApi';

const WS_SUBPROTOCOL = 'meowcloud-collab.v1';

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

    let cancelled = false;
    let socket: WebSocket | null = null;
    initializedRef.current = false;
    canSendUpdatesRef.current = false;

    const sendProjection = () => {
      if (socket && socket.readyState === WebSocket.OPEN && initializedRef.current && canSendUpdatesRef.current) {
        socket.send(JSON.stringify({
          type: 'y_projection',
          content: ytext.toString(),
          state_update: bytesToBase64(Y.encodeStateAsUpdate(ydoc)),
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
      // Only the originating editor projects to the server; doing it for remote
      // updates as well would amplify O(N^2) traffic across a room.
      if (origin !== initOrigin && origin !== remoteOrigin) {
        scheduleProjection();
      }
      if (origin === remoteOrigin || origin === initOrigin) return;
      if (socket && socket.readyState === WebSocket.OPEN && initializedRef.current && canSendUpdatesRef.current) {
        socket.send(JSON.stringify({
          type: 'y_update',
          update: bytesToBase64(update),
        }));
      }
    };

    ydoc.on('update', handleUpdate);

    let attempt = 0;
    let reconnectTimer: number | null = null;
    // A persistent handshake reject surfaces as close code 1006 (the server's
    // 4401/4403 are sent pre-accept and lost), so also cap consecutive attempts
    // to avoid an endless ticket-fetch storm when access is truly gone.
    const MAX_CONNECT_ATTEMPTS = 12;

    const connect = async () => {
      if (cancelled) return;
      try {
        const res = await collaborationApi.wsTicket(fileUuid);
        if (cancelled) return;
        // Ticket is delivered as a WebSocket subprotocol, never in the URL.
        socket = new WebSocket(
          buildWebSocketUrl(`/ws/collab/${fileUuid}`),
          [WS_SUBPROTOCOL, res.ticket],
        );
        wsRef.current = socket;

        socket.onopen = () => {
          attempt = 0;
          setIsConnected(true);
        };

        socket.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            switch (data.type) {
              case 'load_file':
                if (data.y_state) {
                  Y.applyUpdate(ydoc, base64ToBytes(data.y_state), remoteOrigin);
                  initializedRef.current = true;
                  canSendUpdatesRef.current = true;
                } else if ((data.y_updates || []).length > 0) {
                  (data.y_updates || []).forEach((update: string) => {
                    Y.applyUpdate(ydoc, base64ToBytes(update), remoteOrigin);
                  });
                  initializedRef.current = true;
                  canSendUpdatesRef.current = true;
                } else if (data.needs_y_init) {
                  replaceText(ytext, data.content || '', initOrigin);
                  socket?.send(JSON.stringify({
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
                socket?.send(JSON.stringify({
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
              case 'save_error':
                console.error('Save failed:', data.message);
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

        socket.onclose = (ev) => {
          setIsConnected(false);
          initializedRef.current = false;
          if (cancelled) return;
          // 4401/4403 = auth/permission failure: reconnecting cannot help.
          if (ev.code === 4401 || ev.code === 4403) return;
          attempt += 1;
          if (attempt >= MAX_CONNECT_ATTEMPTS) return;
          const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt, 5));
          reconnectTimer = window.setTimeout(() => {
            reconnectTimer = null;
            void connect();
          }, delay);
        };

        socket.onerror = (e) => {
          console.error('WebSocket error:', e);
          setIsConnected(false);
        };
      } catch (e) {
        console.error('WebSocket ticket error:', e);
        setIsConnected(false);
        if (cancelled) return;
        // 401/403/404 from the ticket endpoint = not logged in, revoked, or
        // file gone: retrying cannot help and only hammers the API.
        const status = (e as { response?: { status?: number } })?.response?.status;
        if (status === 401 || status === 403 || status === 404) return;
        attempt += 1;
        if (attempt >= MAX_CONNECT_ATTEMPTS) return;
        const delay = Math.min(30000, 1000 * 2 ** Math.min(attempt, 5));
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = null;
          void connect();
        }, delay);
      }
    };
    void connect();

    return () => {
      cancelled = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (projectionTimerRef.current !== null) {
        window.clearTimeout(projectionTimerRef.current);
        projectionTimerRef.current = null;
      }
      ydoc.off('update', handleUpdate);
      try {
        socket?.close();
      } catch {
        // ignore
      }
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