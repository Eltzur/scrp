/**
 * "Don't count this browser" (SU11A-70). A first-party cookie on every
 * xxl.co.il site, set from the admin console:
 *   xxl_internal=1; Domain=.xxl.co.il; Path=/; Max-Age=1 year; Secure; SameSite=Lax
 * nginx logs only a flag for it ("1" or "-", deploy/nginx/xxl-log-format.conf),
 * never the value, and scripts/stats_logs.py moves those page views out of the
 * counts into internal_page_views. Per browser / phone; it covers website page
 * views only (API calls from this browser are still counted, except the admin
 * console's own, which have their own row).
 */
export const INTERNAL_COOKIE = 'xxl_internal';
export const INTERNAL_MAX_AGE = 365 * 24 * 60 * 60;
const ATTRS = 'Domain=.xxl.co.il; Path=/; Secure; SameSite=Lax';

export function internalCookie(on: boolean): string {
  return on
    ? `${INTERNAL_COOKIE}=1; ${ATTRS}; Max-Age=${INTERNAL_MAX_AGE}`
    : `${INTERNAL_COOKIE}=; ${ATTRS}; Max-Age=0`;
}

export function isInternal(cookie: string): boolean {
  return cookie.split(';').some(c => c.trim() === `${INTERNAL_COOKIE}=1`);
}

export function readInternal(): boolean {
  try { return isInternal(document.cookie); } catch { return false; }
}

/** Sets or deletes the cookie; returns the state read back (false when the
 * browser refused it, e.g. on localhost, which is not under .xxl.co.il). */
export function writeInternal(on: boolean): boolean {
  try {
    document.cookie = internalCookie(on);
  } catch { /* blocked cookies */ }
  return readInternal();
}
