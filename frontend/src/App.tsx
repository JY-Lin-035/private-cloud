import { useEffect, Suspense } from 'react';
import { RouterProvider } from 'react-router-dom';
import router from './router';
import { startVersionWatch } from './utils/versionWatch';
import UpdateToast from './components/UpdateToast';

function App() {
  useEffect(() => startVersionWatch(), []);
  return (
    <>
      <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-gray-900 text-gray-300">載入中…</div>}>
        <RouterProvider router={router} />
      </Suspense>
      <UpdateToast />
    </>
  );
}

export default App;