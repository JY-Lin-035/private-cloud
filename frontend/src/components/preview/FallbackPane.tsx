interface Props {
  filename: string;
  message?: string;
}

/** Shown when a file type has no preview/edit support (or load failed). */
function FallbackPane({ filename, message }: Props) {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-3 text-gray-400 p-8 text-center">
      <div className="text-5xl">📄</div>
      <p className="text-lg">{message ? '無法開啟此檔案' : '此檔案類型不支援線上預覽／編輯'}</p>
      <p className="text-sm break-all max-w-md">{filename}</p>
      {message && <p className="text-sm text-red-400">{message}</p>}
      <p className="text-xs text-gray-500">請關閉後改用下載。</p>
    </div>
  );
}

export default FallbackPane;
