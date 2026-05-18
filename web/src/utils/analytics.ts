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
}

export function trackPageview(path: string): void {
  if (!gaInitialised || !GA_ID) return;
  window.gtag('event', 'page_view', { page_path: path });
}
