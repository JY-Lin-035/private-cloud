import { useEffect, useRef } from 'react';
import Uppy from '@uppy/core';
import Dashboard from '@uppy/dashboard';
import Tus from '@uppy/tus';
import '@uppy/core/css/style.css';
import '@uppy/dashboard/css/style.css';

import { useStorage } from '../../store/storage';
import { API_BASE_URL } from '../../config/api';

const encodeTusMetadata = (value: string) => {
  const bytes = new TextEncoder().encode(value);
  let binary = '';
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
};



interface UpLoadProps {
  parentFolderUuid: string | null;
  onHidden: () => void;
  onRefresh: () => void;
  onComplete: (res: string | string[], cn: string) => void;
}

function UpLoad({ parentFolderUuid, onHidden, onRefresh, onComplete }: UpLoadProps) {
  const storage = useStorage();
  const uppyContainer = useRef<HTMLDivElement>(null);
  const uppyInstance = useRef<Uppy | null>(null);
  // Safari 系不實作 webkitdirectory：隱藏資料夾按鈕並顯示指引，避免拖入資料夾變成 0B 垃圾檔
  const supportsFolderUpload = typeof window !== 'undefined' && 'webkitdirectory' in HTMLInputElement.prototype;

  useEffect(() => {
    if (!uppyContainer.current) return;

    const uppy = new Uppy({
      restrictions: {
        maxFileSize: storage.signalStorage,
        allowedFileTypes: null,
        maxNumberOfFiles: 1000,
      },
      autoProceed: false,
    });

    uppy.use(Dashboard, {
      inline: true,
      target: uppyContainer.current,
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

    uppy.use(Tus, {
      endpoint: `${API_BASE_URL}/api/files/tus`,
      chunkSize: 1024 * 1024 * 50,
      retryDelays: [0, 1000, 3000, 5000],
      withCredentials: true,
      allowedMetaFields: ['name', 'type'],
      headers: (file) => {
        // 按鈕選資料夾時路徑在 data.webkitRelativePath；拖曳資料夾時 Uppy 放在 meta.relativePath
        const relativePath = (file.meta as any)?.relativePath
          || (file.data as File)?.webkitRelativePath
          || '';
        const metadata = [
          `filename ${encodeTusMetadata(file.name || 'unknown')}`,
          `filetype ${encodeTusMetadata(file.type || 'application/octet-stream')}`,
          ...(relativePath ? [`relative_path ${encodeTusMetadata(relativePath)}`] : []),
        ].join(' ');

        return {
          'X-Parent-Folder-Uuid': parentFolderUuid ?? '',
          'Upload-Metadata': metadata,
        };
      },
      removeFingerprintOnSuccess: true,
    });

    uppy.on('file-added', (file) => {
      uppy.setFileMeta(file.id, {
        name: file.name,
        type: file.type || 'application/octet-stream',
        parent_folder_uuid: parentFolderUuid,
      });
    });

    uppy.on('upload-error', (file, error, response: any) => {
      let e = error.message;

      if (response) {
        if (response.body && response.body.message) {
          e = response.body.message;
        } else if (response.status) {
          e = `HTTP ${response.status}: ${response.statusText || e}`;
        }
      }

      alert(`檔案 ${file?.name ?? 'unknown'} 上傳失敗：${e}`);
    });

    uppy.on('complete', (result) => {
      if (!result.failed || result.failed.length === 0) {
        onRefresh();
        onComplete(['上傳完成!'], 'text-green-500');
        storage.getFromAPI();
        uppy.cancelAll();
      }
    });

    uppyInstance.current = uppy;

    return () => {
      if (uppyInstance.current) {
        try {
          uppyInstance.current.cancelAll();
          uppyInstance.current.destroy();
        } catch (e) {
          // console.log(e);
        }
        uppyInstance.current = null;
      }
    };
  }, [parentFolderUuid, storage, onRefresh, onComplete, supportsFolderUpload]);

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onHidden}
      ></div>

      <div className="relative z-10 max-w-[95vw] sm:max-w-[750px]">
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
