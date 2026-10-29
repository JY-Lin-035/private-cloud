declare const __BUILD_TS__: string;
export const APP_VERSION: string = typeof __BUILD_TS__ !== 'undefined' ? __BUILD_TS__ : 'dev';

// Detects a new deployment (version.json differs from the booted build).
// No unsaved edits -> auto reload (once per target version to avoid loops
// through stale edge caches); dirty editor -> asks the user via toast event.
export function startVersionWatch(): () => void {
  let prompted = false;
  const check = async () => {
    try {
      const r = await fetch(`/version.json?nc=${Date.now()}`, { cache: 'no-store' });
      if (!r.ok) return;
      const j = (await r.json()) as { v?: string };
      const remote = j && j.v;
      if (!remote || remote === APP_VERSION) {
        sessionStorage.removeItem('ver-reloaded');
        return;
      }
      if (!(window as unknown as { __appDirty?: boolean }).__appDirty) {
        if (sessionStorage.getItem('ver-reloaded') !== remote) {
          sessionStorage.setItem('ver-reloaded', remote);
          window.location.reload();
        } else if (!prompted) {
          prompted = true;
          window.dispatchEvent(new CustomEvent('meow-update'));
        }
      } else if (!prompted) {
        prompted = true;
        window.dispatchEvent(new CustomEvent('meow-update'));
      }
    } catch { /* offline / proxy hiccup: retry next beat */ }
  };
  const onActive = () => { if (document.visibilityState === 'visible') void check(); };
  document.addEventListener('visibilitychange', onActive);
  window.addEventListener('focus', onActive);
  const timer = window.setInterval(() => void check(), 300_000);
  window.setTimeout(() => void check(), 20_000);
  return () => {
    clearInterval(timer);
    document.removeEventListener('visibilitychange', onActive);
    window.removeEventListener('focus', onActive);
  };
}
