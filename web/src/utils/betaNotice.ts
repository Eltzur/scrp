/**
 * SU11A-75: the "בהרצה" (beta) notice - when it may open on its own.
 *
 * - Hosts: the portal (xxl.co.il / www) and Super (super.xxl.co.il, localhost);
 *   never admin.xxl.co.il or fly.xxl.co.il (fly is another app; checked anyway).
 * - Once per browser: localStorage xxl_notice_beta_v1 = "seen". The key is
 *   versioned so a future text can be shown again under _v2. If storage throws,
 *   once per page load (an in-memory flag).
 * - Never on top of the cookie banner: only when the cookie choice exists. When
 *   storage cannot be read the banner does not show either, so the notice may.
 * - Never on the legal pages, which must stay readable without a popup.
 * The header label reopens it at any time without touching storage.
 */
export const NOTICE_KEY = 'xxl_notice_beta_v1';
export const COOKIE_KEY = 'xxl_cookie_consent';
/** Fired by the header label: open the notice now (no storage change). */
export const NOTICE_OPEN_EVENT = 'xxl:beta-notice-open';

export const LEGAL_PATHS = ['/privacy', '/disclaimer', '/accessibility', '/account/delete'] as const;

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

let seenThisLoad = false;

function storage(): StorageLike | null {
  try { return typeof localStorage === 'undefined' ? null : localStorage; } catch { return null; }
}

export function isNoticeHost(hostname: string): boolean {
  const h = hostname.toLowerCase();
  if (h === 'admin.xxl.co.il' || h === 'fly.xxl.co.il') return false;
  return h === 'xxl.co.il' || h === 'www.xxl.co.il' || h === 'super.xxl.co.il'
    || h === 'localhost' || h === '127.0.0.1';
}

export function isLegalPath(pathname: string): boolean {
  const p = (pathname.replace(/\/+$/, '') || '/').toLowerCase();
  return (LEGAL_PATHS as readonly string[]).includes(p);
}

/** 'answered' (true / false stored), 'pending' (the banner is up) or 'unknown' (storage unreadable: no banner). */
export function cookieChoice(s: StorageLike | null = storage()): 'answered' | 'pending' | 'unknown' {
  if (!s) return 'unknown';
  try {
    const v = s.getItem(COOKIE_KEY);
    return v === 'true' || v === 'false' ? 'answered' : 'pending';
  } catch {
    return 'unknown';
  }
}

export function noticeSeen(s: StorageLike | null = storage()): boolean {
  if (seenThisLoad) return true;
  if (!s) return false;
  try { return s.getItem(NOTICE_KEY) === 'seen'; } catch { return false; }
}

export function markNoticeSeen(s: StorageLike | null = storage()): void {
  seenThisLoad = true;
  try { s?.setItem(NOTICE_KEY, 'seen'); } catch { /* private mode: once per page load */ }
}

/** May the notice open on its own here and now? */
export function shouldAutoShow(hostname: string, pathname: string, s: StorageLike | null = storage(),
                               admin = false): boolean {
  if (admin || !isNoticeHost(hostname) || isLegalPath(pathname)) return false;
  if (noticeSeen(s)) return false;
  return cookieChoice(s) !== 'pending';
}

/** Tests only: forget the in-memory "seen this page load" flag. */
export function _resetNoticeForTests(): void {
  seenThisLoad = false;
}
