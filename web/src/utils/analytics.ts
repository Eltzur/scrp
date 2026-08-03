declare global {
  interface Window {
    dataLayer: unknown[];
    gtag: (...args: unknown[]) => void;
  }
}

const GA_ID = import.meta.env.VITE_GA_MEASUREMENT_ID as string | undefined;
const CONSENT_KEY = 'xxl_cookie_consent';

let gaInitialised = false;

export function hasCookieConsent(): boolean {
  try { return localStorage.getItem(CONSENT_KEY) === 'true'; }
  catch { return false; }
}

export function setCookieConsent(value: boolean): void {
  try { localStorage.setItem(CONSENT_KEY, value ? 'true' : 'false'); }
  catch { /* localStorage blocked in private mode on some browsers */ }
  if (value) initGA();
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
  window.gtag = function (...args) { window.dataLayer.push(args); };
  window.gtag('js', new Date());
  // send_page_view: false — we trigger pageviews manually so SPA navigation works
  window.gtag('config', GA_ID, { send_page_view: false });

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
  trackPageview(window.location.pathname + window.location.search);
}

// Guards the one case where two code paths legitimately race to report the same
// page: on a RETURN visit consent already exists, so App.tsx's mount effect runs
// initGA() (which sends the view above) and then its route-change effect fires
// for the very same location. Suppressing only a CONSECUTIVE repeat keeps real
// A -> B -> A navigation counted, and also absorbs React StrictMode's
// double-invoked effects in development.
let lastTrackedPath: string | null = null;

export function trackPageview(path: string): void {
  if (!gaInitialised || !GA_ID) return;
  if (path === lastTrackedPath) return;
  lastTrackedPath = path;
  window.gtag('event', 'page_view', { page_path: path });
}
