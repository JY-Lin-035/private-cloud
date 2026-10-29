import { useEffect, useState } from 'react';

/** Bottom-right pill offering an immediate reload when a new build is live. */
function UpdateToast() {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const on = () => setShow(true);
    window.addEventListener('meow-update', on);
    return () => window.removeEventListener('meow-update', on);
  }, []);
  if (!show) return null;
  return (
    <button
      type="button"
      onClick={() => window.location.reload()}
      className="fixed bottom-4 right-4 z-[200] px-4 py-2.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-sm shadow-xl cursor-pointer"
    >
      🆕 有新版本，点此重新载入
    </button>
  );
}

export default UpdateToast;
