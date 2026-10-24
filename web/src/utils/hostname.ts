/**
 * Detects whether the current hostname is the portal (xxl.co.il)
 * vs the supermarket app (super.xxl.co.il).
 *
 * Used by App.tsx for route branching and seoMeta.ts for meta-tag selection.
 * Centralised here to avoid duplication.
 */
export function isPortalHostname(): boolean {
  if (typeof window === 'undefined') return false;
  const host = window.location.hostname.toLowerCase();
  // Production portal domains
  if (host === 'xxl.co.il' || host === 'www.xxl.co.il') return true;
  // Local dev override: visit ?portal=1 on localhost to simulate portal hostname
  if (
    (host === 'localhost' || host === '127.0.0.1') &&
    new URLSearchParams(window.location.search).get('portal') === '1'
  ) return true;
  return false;
}

/**
 * SU11A-54: the admin console host. admin.xxl.co.il serves ONLY the admin app
 * (App.tsx). Local dev: ?admin=1 on localhost. The flag is read on every
 * call, so keep it in the URL while testing (a reload without it shows the shop).
 */
export function isAdminHostname(): boolean {
  if (typeof window === 'undefined') return false;
  const host = window.location.hostname.toLowerCase();
  if (host === 'admin.xxl.co.il') return true;
  return (
    (host === 'localhost' || host === '127.0.0.1') &&
    new URLSearchParams(window.location.search).get('admin') === '1'
  );
}
