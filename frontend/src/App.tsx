import { useEffect } from 'react';
import { RouterProvider } from 'react-router-dom';
import router from './router';
import { startVersionWatch } from './utils/versionWatch';
import UpdateToast from './components/UpdateToast';

function App() {
  useEffect(() => startVersionWatch(), []);
  return (
    <>
      <RouterProvider router={router} />
      <UpdateToast />
    </>
  );
}

export default App;