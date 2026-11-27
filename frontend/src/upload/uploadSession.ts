/**
 * Session-scoped upload queue (round 24, PR②).
 *
 * Uppy used to be created inside the upload dialog and destroyed when the
 * dialog closed (`cancelAll()` + `destroy()`), which threw away in-flight
 * resumable uploads — and any 429 in a batch therefore became a wall of
 * per-file failures. The instance is now owned here for the whole signed-in
 * page session; the dialog is only a view that attaches/detaches.
 *
 * Deliberate scope: this promises *navigation-safe* uploads inside one logged
 * in page session. Reload/cross-tab recovery is a separate feature (tus
 * fingerprints are not scoped per account/destination yet).
 */
import Uppy, { type Meta, type UppyFile } from '@uppy/core';
import Tus, { type TusBody } from '@uppy/tus';

import { API_BASE_URL } from '../config/api';
import { UploadCooldown, isRateLimited, statusOf } from './uploadCooldown';

const MAX_PARALLEL_FILES = 3;
const CHUNK_SIZE = 50 * 1024 * 1024;

/**
 * tus-js-client only consults `onShouldRetry` while an entry exists in this
 * array, so the ladder has to be at least as long as the cooldown schedule.
 * The values themselves are 0: the real pacing is the shared rate-limited
 * queue plus the local gate in `onBeforeRequest`, not a per-file timer.
 */
const RETRY_LADDER_MS = new Array(16).fill(0);

export type UploadUppy = Uppy<Meta, TusBody>;
export type UploadFile = UppyFile<Meta, TusBody>;

export interface UploadSession {
  uppy: UploadUppy;
  cooldown: UploadCooldown;
  /** Release the queue after a manual resume (keeps the local gate closed). */
  resumeQueue: () => void;
}

export const encodeTusMetadataValue = (value: string): string => {
  const bytes = new TextEncoder().encode(value);
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
};

let session: UploadSession | null = null;
let sessionOwner: string | null = null;

function ownerKey(): string {
  try {
    return localStorage.getItem('email') || 'anon';
  } catch {
    return 'anon';
  }
}

function build(): UploadSession {
  const cooldown = new UploadCooldown();
  const requestFiles = new WeakMap<object, string>();
  const uppy = new Uppy<Meta, TusBody>({
    autoProceed: false,
    allowMultipleUploadBatches: true,
    restrictions: {
      maxFileSize: -1,
      allowedFileTypes: null,
      maxNumberOfFiles: 1000,
    },
  });

  uppy.use(Tus, {
    endpoint: `${API_BASE_URL}/api/files/tus`,
    chunkSize: CHUNK_SIZE,
    limit: MAX_PARALLEL_FILES,
    withCredentials: true,
    retryDelays: RETRY_LADDER_MS,
    allowedMetaFields: [], // the custom header below is the sole metadata writer
    storeFingerprintForResuming: false,
    urlStorage: {
      findAllUploads: async () => [],
      findUploadsByFingerprint: async () => [],
      removeUpload: async () => {},
      addUpload: async () => '',
    },
    removeFingerprintOnSuccess: true,
    headers: (file) => {
      // Destination is whatever was snapshotted when the file was ADDED, not
      // the folder the user happens to be looking at right now.
      const parentFolderUuid = (file.meta as Record<string, unknown>)?.parent_folder_uuid as
        | string
        | null
        | undefined;
      const relativePath = ((file.meta as Record<string, unknown>)?.relative_path as string)
        || (file.data as File | undefined)?.webkitRelativePath
        || '';
      const metadata = [
        `filename ${encodeTusMetadataValue(file.name || 'unknown')}`,
        `filetype ${encodeTusMetadataValue(file.type || 'application/octet-stream')}`,
        ...(relativePath ? [`relative_path ${encodeTusMetadataValue(relativePath)}`] : []),
      ].join(' ');
      return {
        'X-Parent-Folder-Uuid': parentFolderUuid ?? '',
        'Upload-Metadata': metadata,
      };
    },
    onBeforeRequest: async (request, file) => {
      requestFiles.set(request, file.id);
      while (cooldown.isCooling()) await cooldown.wait();
    },
    onAfterResponse: (request, response) => {
      const status = response.getStatus();
      const method = request.getMethod();
      if (status === 429 && method !== 'DELETE') {
        const decision = cooldown.noteRateLimited();
        const queue = uppy.getPlugin('Tus')?.requests;
        if (queue && decision.action !== 'merged') {
          queue.limit = 1;
          queue.pause(decision.action === 'episode' ? decision.delayMs : null);
        }
      }
      if (method === 'HEAD' && (status < 200 || status >= 300)) {
        // Reject the response before tus-js can discard the existing URL and POST again.
        const message = status === 404 || status === 410
          ? '無法確認此檔案的上傳狀態，請先檢查檔案是否已完成。'
          : `無法取得續傳進度（HTTP ${status}）`;
        throw Object.assign(new Error(message), { status });
      }
      if (method === 'POST' && status === 201) {
        const id = requestFiles.get(request);
        const file = id && uppy.getFile(id);
        const location = response.getHeader('Location');
        if (file && location) {
          const uploadUrl = new URL(location, new URL(request.getURL(), window.location.href)).href;
          uppy.setFileState(file.id, { tus: { ...file.tus, uploadUrl } });
        }
      }
    },
    onShouldRetry: (error, attempt, _options, defaultShouldRetry) => {
      if (isRateLimited(error)) return defaultShouldRetry(error);
      const status = statusOf(error);
      if (status !== null && status >= 400 && status < 500 && status !== 409 && status !== 423) return false;
      return attempt < 3 && defaultShouldRetry(error);
    },
  });

  uppy.on('complete', ({ failed }) => {
    if (!failed?.length && uppy.getFiles().every((file) => file.progress.uploadComplete)) {
      cooldown.noteSuccess();
      const queue = uppy.getPlugin('Tus')?.requests;
      if (queue) queue.limit = MAX_PARALLEL_FILES;
    }
  });

  return {
    uppy,
    cooldown,
    resumeQueue: () => uppy.getPlugin('Tus')?.requests.pause(
      Math.max(0, cooldown.snapshot().resumeAt - Date.now()),
    ),
  };
}

export function getUploadSession(): UploadSession {
  const owner = ownerKey();
  if (session && sessionOwner !== owner) {
    // Account switched without a reload: never let the previous user's queue
    // keep pushing bytes into the new account's folders.
    try {
      session.uppy.cancelAll();
      session.uppy.destroy();
    } catch {
      /* noop */
    }
    session = null;
  }
  sessionOwner = owner;
  if (!session) session = build();
  return session;
}

/** Restrictions follow the signed-in account's quota; called on every mount. */
export function applyUploadRestrictions(maxFileSize: number) {
  const { uppy } = getUploadSession();
  uppy.setOptions({ restrictions: { maxFileSize, allowedFileTypes: null, maxNumberOfFiles: 1000 } });
}

export function disposeUploadSession() {
  if (!session) return;
  try {
    session.uppy.cancelAll();
    session.uppy.destroy();
  } catch {
    /* noop */
  }
  session = null;
  sessionOwner = null;
}
