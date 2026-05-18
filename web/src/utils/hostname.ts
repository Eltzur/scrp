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
