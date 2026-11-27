import { useEffect, useRef, useState } from 'react';
import Dashboard from '@uppy/dashboard';
import type { UploadFile } from '../../upload/uploadSession';
import '@uppy/core/css/style.css';
import '@uppy/dashboard/css/style.css';

import { useStorage } from '../../store/storage';
import { applyUploadRestrictions, getUploadSession } from '../../upload/uploadSession';
import { isRateLimited } from '../../upload/uploadCooldown';
import type { CooldownSnapshot } from '../../upload/uploadCooldown';

interface UpLoadProps {
  parentFolderUuid: string | null;
  onHidden: () => void;
  onRefresh: () => void;
  onComplete: (res: string | string[], cn: string) => void;
}

// Safari 系不實作 webkitdirectory：隱藏資料夾按鈕並顯示指引，避免拖入資料夾變成 0B 垃圾檔
const supportsFolderUpload = typeof window !== 'undefined'
  && 'webkitdirectory' in HTMLInputElement.prototype;

function UpLoad({ parentFolderUuid, onHidden, onRefresh, onComplete }: UpLoadProps) {
  const storage = useStorage();
  const uppyContainer = useRef<HTMLDivElement>(null);
  const [cooldown, setCooldown] = useState<CooldownSnapshot | null>(null);
  const [pending, setPending] = useState(0);
  const resumeButton = useRef<null | (() => void)>(null);
  // The dialog is a view only: the queue lives in uploadSession so closing it
  // never throws away uploads that are running or waiting out a 429 cooldown.
  const cbs = useRef({ onRefresh, onComplete, storage });
  useEffect(() => {
    cbs.current = { onRefresh, onComplete, storage };
  }, [onRefresh, onComplete, storage]);

  useEffect(() => {
    const { uppy, cooldown: gate, resumeQueue } = getUploadSession();
    applyUploadRestrictions(storage.signalStorage);

    const sync = () => {
      setCooldown(gate.snapshot());
      setPending(uppy.getFiles().filter((f) => !f.progress.uploadComplete && !f.error).length);
    };
    const unsubscribe = gate.subscribe(sync);
    sync();

    const onFileAdded = (file: UploadFile) => {
      // Destination and path are pinned here (enqueue time), so navigating to
      // another folder while a batch is queued cannot re-target the leftovers.
      const relativePath = (file.meta.relativePath as string | undefined)
        || (file.data as File | undefined)?.webkitRelativePath
        || '';
      uppy.setFileMeta(file.id, {
        name: file.name,
        type: file.type || 'application/octet-stream',
        parent_folder_uuid: parentFolderUuid,
        relative_path: relativePath,
      });
      sync();
    };

    const onUploadError = (file: UploadFile | undefined, error: { message?: string }) => {
      // A 429 is a batch condition, not a per-file fault: the cooldown banner
      // says it once instead of one alert dialog per file.
      if (!isRateLimited(error)) {
        alert(`檔案 ${file?.name ?? 'unknown'} 上傳失敗：${(error as Error)?.message ?? error}`);
      }
      sync();
    };

    const onComplete_ = (result: { failed?: UploadFile[]; successful?: UploadFile[] }) => {
      const ok = result.successful?.length ?? 0;
      const failed = result.failed?.length ?? 0;
      if (ok > 0) {
        cbs.current.onRefresh();
        void cbs.current.storage.getFromAPI();
      }
      if (failed === 0 && ok > 0) {
        cbs.current.onComplete(['上傳完成!'], 'text-green-500');
        uppy.removeFiles(result.successful?.map((file) => file.id) ?? []);
      }
      sync();
    };

    uppy.on('file-added', onFileAdded);
    uppy.on('file-removed', sync);
    uppy.on('upload-progress', sync);
    uppy.on('upload-error', onUploadError);
    uppy.on('complete', onComplete_);

    uppy.use(Dashboard, {
      inline: true,
      target: uppyContainer.current ?? undefined,
      proudlyDisplayPoweredByUppy: false,
      fileManagerSelectionType: supportsFolderUpload ? 'both' : 'files',
      locale: {
        strings: {
          dropPasteFiles: '請將檔案拖曳到這裡或 %{browseFiles}',
          browseFiles: '選擇檔案',
          browseFolders: '選擇資料夾',
        },
      },
    });
    const dashboard = uppy.getPlugin('Dashboard');
    sync();

    const onManualResume = () => {
      gate.resumeManually(); // keeps the local gate closed for its floor delay
      resumeQueue();
      void uppy.retryAll().catch(() => { /* reported per file */ });
      sync();
    };
    resumeButton.current = onManualResume;

    return () => {
      uppy.off('file-added', onFileAdded);
      uppy.off('file-removed', sync);
      uppy.off('upload-progress', sync);
      uppy.off('upload-error', onUploadError);
      uppy.off('complete', onComplete_);
      unsubscribe();
      resumeButton.current = null;
      try {
        // Detach the view; the queue and its uploads keep running.
        if (dashboard) uppy.removePlugin(dashboard);
      } catch (e) {
        console.warn('uppy dashboard detach failed', e);
      }
    };
  }, [parentFolderUuid, storage]);

  const cooling = Boolean(cooldown?.cooling);
  const exhausted = Boolean(cooldown?.exhausted);

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onHidden}
      ></div>

      <div className="relative z-10 max-w-[95vw] sm:max-w-[750px]">
        {cooling && (
          <div
            role="status"
            className="mb-2 rounded-lg bg-amber-500/15 border border-amber-400/40 px-3 py-2 text-amber-200 text-sm flex items-center justify-between gap-3"
          >
            <span>
              {exhausted
                ? `伺服器暫時限流，佇列已保留 ${pending} 個檔案，待你手動續傳。`
                : `伺服器暫時限流，整批上傳暫停退避中（第 ${cooldown?.episodes ?? 0} 次），稍後自動續傳。`}
            </span>
            {exhausted && (
              <button
                onClick={() => resumeButton.current?.()}
                className="shrink-0 px-3 py-1 rounded bg-amber-400 text-black font-medium cursor-pointer"
              >
                繼續上傳
              </button>
            )}
          </div>
        )}
        <div ref={uppyContainer}></div>
        {!supportsFolderUpload && (
          <p className="text-amber-200 text-xs mt-2 text-center">
            此瀏覽器不支援資料夾上傳：請改用 Chrome / Firefox，或先將資料夾壓縮成 zip 後以單一檔案上傳。
          </p>
        )}
      </div>
    </div>
  );
}

export default UpLoad;
