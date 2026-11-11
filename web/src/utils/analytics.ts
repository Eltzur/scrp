declare global {
  interface Window {
    dataLayer: unknown[];
    gtag: (...args: unknown[]) => void;
  }
}

const GA_ID = import.meta.env.VITE_GA_MEASUREMENT_ID as string | undefined;
const CONSENT_KEY = 'xxl_cookie_consent';

let gaInitialised = false;

/**
 * The path only: never the query string or the hash (SU11A-71). Search and
 * promo pages carry what users typed or chose (?q=..., ?city=...), and GA4 must
 * not receive it - the same rule as the server statistics.
 */
export function pathOnly(path: string): string {
  const p = path.split(/[?#]/, 1)[0];
  return p.startsWith('/') ? p : `/${p}`;
}

/** The external referrer reduced to its origin ("https://www.google.com/"), or ''. */
function referrerOrigin(): string {
  try { return document.referrer ? `${new URL(document.referrer).origin}/` : ''; }
  catch { return ''; }
}

/**
 * Google's documented per-property opt-out: while true, gtag.js sends nothing
 * for GA_ID (including its own automatic events). Set on decline / withdrawal,
 * cleared on accept, so withdrawing consent also stops a tag already loaded.
 */
function setGaDisabled(disabled: boolean): void {
  if (!GA_ID) return;
  (window as unknown as Record<string, unknown>)[`ga-disable-${GA_ID}`] = disabled;
}

export function hasCookieConsent(): boolean {
  try { return localStorage.getItem(CONSENT_KEY) === 'true'; }
  catch { return false; }
}

export function setCookieConsent(value: boolean): void {
  try { localStorage.setItem(CONSENT_KEY, value ? 'true' : 'false'); }
  catch { /* localStorage blocked in private mode on some browsers */ }
  setGaDisabled(!value);
  if (value) initGA();
  // SU11A-75: the beta notice waits for the cookie choice and opens right after it.
  try { window.dispatchEvent(new Event(COOKIE_CHOICE_EVENT)); } catch { /* no window */ }
}

/** Fired after a cookie choice is stored (accept or decline). */
export const COOKIE_CHOICE_EVENT = 'xxl:cookie-choice';

/** Fired to ask a mounted CookieBanner to show itself again. */
export const COOKIE_PREFS_EVENT = 'xxl:cookie-preferences';

/**
 * Manual re-entry to the consent choice.
 *
 * Declining wrote 'false', which satisfies neither the banner's render test
 * (key absent) nor the GA gate (key === 'true'), so a declined visitor had no
 * banner and no analytics and no way back — the documented escape was "clear
 * your browser's site data". This clears the stored choice and re-opens the
 * banner so the decision can be made again.
 *
 * Deliberately user-initiated only: nothing calls this automatically, so a
 * decline is still respected and never re-prompted on its own.
 */
export function openCookiePreferences(): void {
  try { localStorage.removeItem(CONSENT_KEY); }
  catch { /* private mode */ }
  setGaDisabled(true);
  window.dispatchEvent(new Event(COOKIE_PREFS_EVENT));
}

/**
 * Injects the gtag.js script if:
 *  - A valid (non-placeholder) measurement ID is configured, AND
 *  - The user has given cookie consent.
 * Idempotent — safe to call multiple times.
 */
export function initGA(): void {
  if (gaInitialised) return;
  if (!GA_ID || GA_ID === 'G-PLACEHOLDER') {
    console.warn('[analytics] VITE_GA_MEASUREMENT_ID not set or placeholder — GA4 not loaded.');
    return;
  }
  if (!hasCookieConsent()) return;

  // Inject gtag.js
  window.dataLayer = window.dataLayer || [];
  // SU11A-71: Google's canonical shim. gtag.js processes only Arguments
  // objects from dataLayer; the former `(...args) => dataLayer.push(args)`
  // pushed Arrays, which gtag.js silently ignores - so js / config / page_view
  // never reached GA4 and no hit was ever sent (property empty since launch).
  window.gtag = function gtag() {
    // eslint-disable-next-line prefer-rest-params
    window.dataLayer.push(arguments);
  };
  setGaDisabled(false);
  window.gtag('js', new Date());
  // send_page_view: false - we send page views ourselves (one per route).
  // page_location / page_referrer override gtag's defaults (the full
  // document.location and document.referrer, query string included) for every
  // event of this tag, its automatic ones too.
  window.gtag('config', GA_ID, {
    send_page_view: false,
    page_location: window.location.origin + pathOnly(window.location.pathname),
    page_referrer: referrerOrigin(),
  });

  const script = document.createElement('script');
  script.async = true;
  script.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
  document.head.appendChild(script);

  gaInitialised = true;

  // Send the page_view for the page the user is ALREADY on.
  //
  // Without this, a first-time visitor sends nothing at all: both mount effects
  // in App.tsx run before consent exists, so initGA() and trackPageview() each
  // bail out; clicking accept then calls initGA() but nothing calls
  // trackPageview() again. Since config sets send_page_view:false, GA received
  // only `js` and `config` — no event — so a session that accepted and read one
  // page was invisible. Page views previously began at the user's SECOND
  // navigation.
  trackPageview(window.location.pathname);
}

// Guards the one case where two code paths legitimately race to report the same
// page: on a RETURN visit consent already exists, so App.tsx's mount effect runs
// initGA() (which sends the view above) and then its route-change effect fires
// for the very same location. Suppressing only a CONSECUTIVE repeat keeps real
// A -> B -> A navigation counted, and also absorbs React StrictMode's
// double-invoked effects in development.
//
// SU11A-71: the comparison is on the PATH only. A query-only change
// (/promos -> /promos?city=..., the page's own history.replace, or a new
// search on the same page) is not a new page view; /promos fired 3 page_views
// in one visit before this.
let lastTrackedPath: string | null = null;

export function trackPageview(rawPath: string): void {
  if (!gaInitialised || !GA_ID) return;
  // Re-checked at send time, not just at init. Until now consent could only be
  // granted once and never revisited, so an already-initialised tag could not
  // outlive its permission. The preferences control makes accept-then-decline
  // reachable within one page session, and gtag.js stays loaded once injected —
  // without this the tag would keep reporting after the user withdrew consent.
  if (!hasCookieConsent()) return;
  const path = pathOnly(rawPath);
  if (path === lastTrackedPath) return;
  const page_referrer = lastTrackedPath === null
    ? referrerOrigin()
    : window.location.origin + lastTrackedPath;
  lastTrackedPath = path;
  const page_location = window.location.origin + path;
  // `set` keeps gtag's automatic events (user_engagement, scroll...) on the
  // same path-only values; the event carries them explicitly as well.
  window.gtag('set', { page_location, page_referrer });
  window.gtag('event', 'page_view', { page_path: path, page_location, page_referrer });
}
