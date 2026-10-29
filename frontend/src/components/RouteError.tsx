import { useRouteError, isRouteErrorResponse } from 'react-router-dom';
import { useEffect } from 'react';

/**
 * Root errorElement: lazily-imported chunk failures happen when an old
 * index.html references rotated-away assets (deploy race). One silent
 * auto-reload fixes it; further failures show a friendly retry card.
 */
function RouteError() {
  const error = useRouteError();
  const msg = isRouteErrorResponse(error) ? `${error.status} ${error.statusText}` : String((error as Error)?.message || error);
  const chunkFail = /dynamically imported|Failed to fetch|Importing a module script failed|Loading chunk/i.test(msg);

  useEffect(() => {
    if (chunkFail && !sessionStorage.getItem('chunk-reload')) {
      sessionStorage.setItem('chunk-reload', '1');
      window.location.reload();
    }
  }, [chunkFail]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-gray-900 text-gray-200 p-8 text-center">
      <div className="text-5xl">🐈</div>
      <p className="text-lg">頁面元件載入失敗（通常因為新版本部署）</p>
      <p className="text-sm text-gray-500 max-w-md break-all">{msg.slice(0, 160)}</p>
      <button type="button" className="px-5 py-2 rounded bg-blue-600 hover:bg-blue-500 text-white"
        onClick={() => window.location.reload()}>
        重新載入
      </button>
    </div>
  );
}

export default RouteError;
