import { useState, useMemo } from 'react';
import { Modal, Input, Button } from 'antd';

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
    <Modal
      open={showMode}
      onCancel={onClose}
      footer={null}
      centered
      className="notices-modal"
    >
      <div className="p-4 text-center md:p-5">
        <svg
          className={`w-12 h-12 mx-auto mb-6 ${className}`}
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
            <Input
              value={localFolderName}
              onChange={(e) => {
                setLocalFolderName(e.target.value);
                onUpdateFolderName?.(e.target.value);
              }}
              placeholder="請輸入資料夾名稱"
              className="w-full mb-6"
            />

            {!valFolderName && localFolderName !== '' && (
              <p className="text-red-500 text-[1.5rem]">
                *僅接受中、英、數，不接受任何符號，且以 30 字元為限
              </p>
            )}
          </>
        )}

        <Button
          onClick={handleBT}
          type="primary"
          className="mt-6"
          disabled={inputShow && (!valFolderName || localFolderName === '')}
          block
        >
          OK!
        </Button>
      </div>
    </Modal>
  );
}

export default Notices;
