import { isPortalHostname } from './hostname';
import { PLAY_APP_ID, PLAY_STORE_URL } from '../config/apps';

/**
 * Per-route head tags (SU11A-46): title, description, canonical, Open Graph /
 * Twitter, and robots noindex.
 *
 * App calls applyRouteMeta(pathname) from its own effect on every route change.
 * App is the parent of every page, so its effect runs after the pages' effects
 * and nothing else writes these tags: pages no longer set document.title
 * themselves (the old "one tick late" workarounds are gone).
 *
 * One web build serves both hosts (xxl.co.il / www and super.xxl.co.il), so a
 * route's canonical depends on where the page belongs:
 *   portal  - always https://xxl.co.il/...        (portal-only pages)
 *   super   - always https://super.xxl.co.il/...  (the supermarket app; also
 *             when its routes are opened on xxl.co.il)
 *   current - the host it was opened on           (legal pages exist on both)
 * www.xxl.co.il always canonicalises to the apex; the query string is dropped.
 * localhost maps to the production host it simulates (?portal=1 = portal).
 * The sitemaps in web/public list exactly the indexable URLs below.
 *
 * SU11A-53: every page served on the super host carries
 * <meta name="google-play-app" content="app-id=...">, and the super home adds
 * a SoftwareApplication JSON-LD block for the Android app. No apple-itunes-app
 * meta until the iOS app is live. (Head tags only: the inline script in
 * index.html is untouched, its CSP hash stays valid; a JSON-LD data block is
 * not script and needs no script-src entry.)
 */

const PORTAL_ORIGIN = 'https://xxl.co.il';
const SUPER_ORIGIN = 'https://super.xxl.co.il';

type Home = 'portal' | 'super' | 'current';

interface RouteMeta {
  title: string;
  description: string;
  home: Home;
  noindex?: boolean;
}

const PORTAL_HOME_TITLE = 'XXL — הפורטל שהופך כסף רגיל לכסף חכם';
const PORTAL_HOME_DESC = 'השוואת מחירים חכמה למצרכים, חופשות ואופנה. חוסכים בענקקק.';
const SUPER_HOME_TITLE = 'XXL — השוואת מחירים בסופרמרקט · חוסכים בענקקק';
const SUPER_HOME_DESC = 'השוואת מחירים בין סופרמרקטים בישראל. שופרסל, רמי לוי, יוחננוף, ויקטורי, אושר עד, קשת, קרפור. חוסכים בענקקק.';

// Supermarket routes (AppShell). '/' is resolved per host below.
const SUPER_ROUTES: Record<string, RouteMeta> = {
  '/promos': {
    title: 'מבצעים בסופרמרקטים | SUPER XXL',
    description: 'מבצעי השבוע ברשתות השיווק בישראל לפי עיר, רשת וסניף: שופרסל, רמי לוי, יוחננוף, ויקטורי ועוד.',
    home: 'super',
  },
  '/login': { title: 'התחברות | SUPER XXL', description: 'התחברות לחשבון SUPER XXL.', home: 'super', noindex: true },
  '/signup': { title: 'הרשמה | SUPER XXL', description: 'פתיחת חשבון ב-SUPER XXL.', home: 'super', noindex: true },
  '/reset-password': { title: 'איפוס סיסמה | SUPER XXL', description: 'איפוס הסיסמה לחשבון SUPER XXL בקוד שנשלח במייל.', home: 'super', noindex: true },
  '/account/delete': { title: 'מחיקת חשבון | SUPER XXL', description: 'איך מוחקים את החשבון ב-SUPER XXL ואילו נתונים נמחקים.', home: 'super', noindex: true },
  '/baskets': { title: 'הסלים שלי | SUPER XXL', description: 'סלי הקניות השמורים שלך.', home: 'super', noindex: true },
  '/favorites': { title: 'המועדפים שלי | SUPER XXL', description: 'המוצרים שסימנת כמועדפים.', home: 'super', noindex: true },
  '/my-ratings': { title: 'הדירוגים שלי | SUPER XXL', description: 'הדירוגים שכתבת למוצרים.', home: 'super', noindex: true },
};

// Pages registered outside AppShell. Legal titles take the host's brand.
function standaloneMeta(path: string, brand: string): RouteMeta | null {
  switch (path) {
    case '/privacy':
      return { title: `מדיניות פרטיות | ${brand}`, description: 'איזה מידע XXL אוספת באתר ובאפליקציה, למה, כמה זמן הוא נשמר ואיך מוחקים אותו.', home: 'current' };
    case '/disclaimer':
      return { title: `תנאי שימוש | ${brand}`, description: 'תנאי השימוש וכתב הוויתור של XXL ו-SUPER XXL, כולל כללי הדירוגים והתגובות.', home: 'current' };
    case '/accessibility':
      return { title: `הצהרת נגישות | ${brand}`, description: 'הצהרת הנגישות של XXL: רמת ההתאמה, מגבלות ידועות ודרכי פנייה בנושא נגישות.', home: 'current' };
    case '/partnerships':
      return { title: 'שיתופי פעולה | XXL', description: 'XXL פתוחה לשיתופי פעולה: נתונים, API, MCP ועוד.', home: 'portal' };
    case '/fashion':
      return { title: 'אופנה — בקרוב | XXL', description: 'השוואת מחירים לבגדים ולנעליים — בקרוב ב-XXL.', home: 'portal', noindex: true };
    case '/portal-preview':
      return { title: PORTAL_HOME_TITLE, description: PORTAL_HOME_DESC, home: 'portal', noindex: true };
    default:
      return null;
  }
}

export interface ResolvedMeta {
  title: string;
  description: string;
  /** Absolute canonical URL, or null for an unknown path. */
  canonical: string | null;
  noindex: boolean;
  image: string;
  /** content of <meta name="google-play-app">, or null (portal host). */
  playApp: string | null;
  /** SoftwareApplication JSON-LD for the super home, else null. */
  jsonLd: Record<string, unknown> | null;
}

/** The Android app, as schema.org SoftwareApplication (super home only). */
export const APP_JSON_LD: Record<string, unknown> = {
  '@context': 'https://schema.org',
  '@type': 'SoftwareApplication',
  name: 'SUPER XXL',
  operatingSystem: 'ANDROID',
  applicationCategory: 'ShoppingApplication',
  url: PLAY_STORE_URL,
  offers: { '@type': 'Offer', price: '0', priceCurrency: 'ILS' },
  publisher: { '@type': 'Organization', name: 'XXL Team' },
};

/** Pure: the head tags for a path on the given kind of host. */
export function resolveRouteMeta(pathname: string, portalHost: boolean): ResolvedMeta {
  const path = pathname.length > 1 ? pathname.replace(/\/+$/, '') : '/';
  const brand = portalHost ? 'XXL' : 'SUPER XXL';
  let meta: RouteMeta | null;
  if (path === '/') {
    meta = portalHost
      ? { title: PORTAL_HOME_TITLE, description: PORTAL_HOME_DESC, home: 'portal' }
      : { title: SUPER_HOME_TITLE, description: SUPER_HOME_DESC, home: 'super' };
  } else {
    meta = standaloneMeta(path, brand) ?? SUPER_ROUTES[path] ?? null;
  }
  const currentOrigin = portalHost ? PORTAL_ORIGIN : SUPER_ORIGIN;
  const playApp = portalHost ? null : `app-id=${PLAY_APP_ID}`;
  const jsonLd = !portalHost && path === '/' ? APP_JSON_LD : null;
  if (!meta) {
    // Unknown path: the SPA fallback answers 200 with the app shell. Keep it
    // out of the index and give it no canonical.
    return {
      title: portalHost ? PORTAL_HOME_TITLE : SUPER_HOME_TITLE,
      description: portalHost ? PORTAL_HOME_DESC : SUPER_HOME_DESC,
      canonical: null,
      noindex: true,
      image: `${currentOrigin}/${portalHost ? 'og-portal.png' : 'og-super.png'}`,
      playApp,
      jsonLd: null,
    };
  }
  const origin = meta.home === 'portal' ? PORTAL_ORIGIN : meta.home === 'super' ? SUPER_ORIGIN : currentOrigin;
  return {
    title: meta.title,
    description: meta.description,
    canonical: origin + (path === '/' ? '/' : path),
    noindex: !!meta.noindex,
    image: `${origin}/${origin === PORTAL_ORIGIN ? 'og-portal.png' : 'og-super.png'}`,
    playApp,
    jsonLd,
  };
}

function setMeta(attr: 'name' | 'property', key: string, value: string): void {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[${attr}="${key}"]`);
  if (!el) {
    el = document.createElement('meta');
    el.setAttribute(attr, key);
    document.head.appendChild(el);
  }
  el.setAttribute('content', value);
}

/** Writes the head tags for the current host and this path. Idempotent. */
export function applyRouteMeta(pathname: string): void {
  const m = resolveRouteMeta(pathname, isPortalHostname());
  document.title = m.title;
  setMeta('name', 'description', m.description);
  setMeta('property', 'og:title', m.title);
  setMeta('property', 'og:description', m.description);
  setMeta('property', 'og:image', m.image);
  setMeta('name', 'twitter:title', m.title);
  setMeta('name', 'twitter:description', m.description);
  setMeta('name', 'twitter:image', m.image);

  let link = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]');
  if (m.canonical) {
    if (!link) {
      link = document.createElement('link');
      link.rel = 'canonical';
      document.head.appendChild(link);
    }
    link.href = m.canonical;
    setMeta('property', 'og:url', m.canonical);
  } else {
    link?.remove();
    document.head.querySelector('meta[property="og:url"]')?.remove();
  }

  const robots = document.head.querySelector('meta[name="robots"]');
  if (m.noindex) setMeta('name', 'robots', 'noindex');
  else robots?.remove();

  if (m.playApp) setMeta('name', 'google-play-app', m.playApp);
  else document.head.querySelector('meta[name="google-play-app"]')?.remove();

  let ld = document.head.querySelector<HTMLScriptElement>('script#ld-app');
  if (m.jsonLd) {
    if (!ld) {
      ld = document.createElement('script');
      ld.type = 'application/ld+json';
      ld.id = 'ld-app';
      document.head.appendChild(ld);
    }
    ld.textContent = JSON.stringify(m.jsonLd);
  } else {
    ld?.remove();
  }
}
