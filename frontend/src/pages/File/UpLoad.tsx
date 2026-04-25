import { useEffect, useRef } from 'react';
import Uppy from '@uppy/core';
import Dashboard from '@uppy/dashboard';
import XHRUpload from '@uppy/xhr-upload';
import '@uppy/core/css/style.css';
import '@uppy/dashboard/css/style.css';

import { useStorage } from '../../store/storage';
import { API_BASE_URL } from '../../config/api';



interface UpLoadProps {
  PATH: string;
  onHidden: () => void;
  onRefresh: () => void;
  onComplete: (res: string | string[], cn: string) => void;
}

function UpLoad({ PATH, onHidden, onRefresh, onComplete }: UpLoadProps) {
  const storage = useStorage();
  const uppyContainer = useRef<HTMLDivElement>(null);
  const uppyInstance = useRef<Uppy | null>(null);

  useEffect(() => {
    if (!uppyContainer.current) return;

    const uppy = new Uppy({
      restrictions: {
        maxFileSize: storage.signalStorage,
        allowedFileTypes: null,
        maxNumberOfFiles: 3,
      },
      autoProceed: false,
    });

    uppy.use(Dashboard, {
      inline: true,
      target: uppyContainer.current,
      proudlyDisplayPoweredByUppy: false,
      locale: {
        strings: {
          dropPasteFiles: '請將檔案拖曳到這裡或 %{browseFiles}',
          browseFiles: '選擇檔案',
        },
      },
    });

    uppy.use(XHRUpload, {
      endpoint: `${API_BASE_URL}/api/files/uploadFile`,
      formData: true,
      fieldName: 'file',
      bundle: false,
      withCredentials: true,
    });

    uppy.on('file-added', (file) => {
      uppy.setFileMeta(file.id, {
        dir: PATH,
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

      alert(`檔案 ${file.name} 上傳失敗：${e}`);
    });

    uppy.on('complete', (result) => {
      if (result.failed.length === 0) {
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
  }, [PATH, storage, onRefresh, onComplete]);

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onHidden}
      ></div>

      <div className="relative z-10">
        <div ref={uppyContainer}></div>
      </div>
    </div>
  );
}

export default UpLoad;
