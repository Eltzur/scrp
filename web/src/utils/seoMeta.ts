import { isPortalHostname } from './hostname';

function setMeta(selector: string, value: string): void {
  document.querySelector(selector)?.setAttribute('content', value);
}

/**
 * Applies hostname-appropriate title, description, OG, and Twitter meta tags.
 * Static fallbacks in index.html default to portal values; this function
 * overwrites to supermarket-app values on super.xxl.co.il.
 * Safe to call multiple times (idempotent).
 */
export function applyHostnameMeta(): void {
  if (isPortalHostname()) {
    // Portal hostname — index.html static defaults already correct; reinforce them
    document.title = 'XXL — הפורטל שהופך כסף רגיל לכסף חכם';
    setMeta('meta[name="description"]',            'השוואת מחירים חכמה למצרכים, חופשות ואופנה. חוסכים בענקקק.');
    setMeta('meta[property="og:title"]',           'XXL — הפורטל שהופך כסף רגיל לכסף חכם');
    setMeta('meta[property="og:description"]',     'השוואת מחירים חכמה למצרכים, חופשות ואופנה. חוסכים בענקקק.');
    setMeta('meta[property="og:url"]',             'https://xxl.co.il');
    setMeta('meta[property="og:image"]',           'https://xxl.co.il/og-portal.png');
    setMeta('meta[name="twitter:title"]',          'XXL — הפורטל שהופך כסף רגיל לכסף חכם');
    setMeta('meta[name="twitter:description"]',    'השוואת מחירים חכמה למצרכים, חופשות ואופנה.');
    setMeta('meta[name="twitter:image"]',          'https://xxl.co.il/og-portal.png');
  } else {
    // Supermarket app — super.xxl.co.il
    const title       = 'XXL — השוואת מחירים בסופרמרקט · חוסכים בענקקק';
    const description = 'השוואת מחירים בין סופרמרקטים בישראל. שופרסל, רמי לוי, יוחננוף, ויקטורי, אושר עד, קשת, קרפור. חוסכים בענקקק.';
    document.title = title;
    setMeta('meta[name="description"]',            description);
    setMeta('meta[property="og:title"]',           title);
    setMeta('meta[property="og:description"]',     description);
    setMeta('meta[property="og:url"]',             'https://super.xxl.co.il');
    setMeta('meta[property="og:image"]',           'https://super.xxl.co.il/og-super.png');
    setMeta('meta[name="twitter:title"]',          title);
    setMeta('meta[name="twitter:description"]',    description);
    setMeta('meta[name="twitter:image"]',          'https://super.xxl.co.il/og-super.png');
  }
}
