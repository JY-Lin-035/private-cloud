import { useState, useMemo, useEffect } from 'react';

interface NoticesProps {
  inputShow?: boolean;
  folderName?: string;
  notices: string | string[];
  showMode: boolean;
  className: string;
  onClose?: () => void;
  onUpdateFolderName?: (value: string) => void;
  onEmitFolderName?: () => void;
}

function Notices({
  inputShow = false,
  folderName = '',
  notices,
  showMode,
  className,
  onClose,
  onUpdateFolderName,
  onEmitFolderName,
}: NoticesProps) {
  const [localFolderName, setLocalFolderName] = useState(folderName);

  useEffect(() => {
    setLocalFolderName(folderName);
  }, [folderName]);

  const valFolderName = useMemo(() => /^[A-Za-z0-9\p{Script=Han}]{1,30}$/u.test(localFolderName), [localFolderName]);

  function handleBT() {
    if (inputShow) {
      onEmitFolderName?.();
    } else {
      onClose?.();
    }
  }

  const noticesArray = Array.isArray(notices) ? notices : [notices];

  return (
    <>
      {showMode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="fixed inset-0 bg-black/50"
            onClick={onClose}
          ></div>
          <div className="relative z-10 w-full max-w-[40vw] max-h-[80vh] overflow-y-auto p-6 rounded-lg shadow-xl bg-gray-800">
            <button
              onClick={onClose}
              className="absolute top-3 right-2.5 text-gray-400 bg-transparent hover:bg-gray-700 hover:text-white rounded-lg text-sm w-8 h-8 flex items-center justify-center"
            >
              <svg className="w-3 h-3" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 14 14">
                <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m1 1 6 6m0 0 6 6M7 7l6-6M7 7l-6 6" />
              </svg>
            </button>

            <div className="p-4 text-center md:p-5 text-white">
              <svg
                className="w-12 h-12 mx-auto mb-6"
                aria-hidden="true"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 20 20"
              >
                <path
                  stroke="currentColor"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M10 11V6m0 8h.01M19 10a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"
                />
              </svg>

              {noticesArray.map((notice, index) => (
                <h3
                  key={index}
                  className={`mb-5 text-xl font-normal ${className}`}
                >
                  {notice}
                </h3>
              ))}

              {inputShow && (
                <>
                  <input
                    type="text"
                    value={localFolderName}
                    onChange={(e) => {
                      setLocalFolderName(e.target.value);
                      onUpdateFolderName?.(e.target.value);
                    }}
                    placeholder="請輸入資料夾名稱"
                    className="w-full px-3 py-2 mt-6 mb-6 border rounded bg-white text-gray-900 border-gray-300"
                  />

                  {!valFolderName && localFolderName !== '' && (
                    <p className="text-red-500 text-[1.5rem]">
                      *僅接受中、英、數，不接受任何符號，且以 30 字元為限
                    </p>
                  )}
                </>
              )}

              <button
                onClick={handleBT}
                type="button"
                className="text-white bg-blue-600 hover:bg-blue-500 focus:ring-4 focus:outline-none focus:ring-blue-300 font-medium rounded-lg text-lg inline-flex items-center justify-center px-5 py-2.5 mt-6 text-center"
                disabled={inputShow && (!valFolderName || localFolderName === '')}
              >
                OK!
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default Notices;
