// Static-landing visibility hook: the SEO hero/footer blocks live OUTSIDE
// #app (raw HTML in index.html) so crawlers and logged-out visitors see a
// real landing page. Once a session is verified (or a login succeeds) we
// toggle this class; CSS hides the blocks and the app UI is all that shows.
export function setAuthedUI(authed: boolean): void {
  document.body.classList.toggle('sl-authed', authed);
}
