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
import { UploadCooldown, isRateLimited } from './uploadCooldown';

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
    allowedMetaFields: ['name', 'type'],
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
    onBeforeRequest: async () => {
      // Local gate: while the batch is cooling down nothing new leaves the
      // browser — including the HEAD that a resume needs, which tus-js would
      // otherwise turn into a brand new POST when the server answers 429.
      await cooldown.wait();
    },
    onShouldRetry: (error, _attempt, _options, defaultShouldRetry) => {
      if (!isRateLimited(error)) return defaultShouldRetry(error);
      const decision = cooldown.noteRateLimited();
      const requests = tusRequests(uppy);
      if (!requests) return true;
      if (decision.action === 'exhausted') {
        requests.pause(null); // frozen: only a manual resume opens it again
      } else {
        // pauses the WHOLE batch and drops concurrency to one request, then
        // ramps back up — the "release a trickle first" behaviour.
        requests.rateLimit(decision.delayMs);
      }
      // Let @uppy/tus do its requeue bookkeeping; the queue is already paused
      // so it will not spend its own (shared) retry ladder entry.
      return defaultShouldRetry(error);
    },
  });

  // Any file that finishes proves the limiter has released us again.
  uppy.on('upload-success', () => cooldown.noteSuccess());

  return {
    uppy,
    cooldown,
    resumeQueue: () => tusRequests(uppy)?.resume(),
  };
}

function tusRequests(uppy: UploadUppy) {
  const tus = uppy.getPlugin('Tus') as { requests?: RateLimitedLike } | undefined;
  return tus?.requests;
}

interface RateLimitedLike {
  rateLimit: (ms: number) => void;
  pause: (ms?: number | null) => void;
  resume: () => void;
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
