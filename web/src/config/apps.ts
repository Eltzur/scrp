/**
 * Store links for the SUPER XXL mobile app (SU11A-53). One place for the web.
 *
 * SU11A-70: the iOS app is live on the App Store (Israel storefront), so the
 * site links to it with Apple's official badge (public/badges/SOURCE.txt):
 * unaltered, black, localised to the page language.
 */
export const PLAY_APP_ID = 'il.co.xxl.supermarket';
export const PLAY_STORE_URL = `https://play.google.com/store/apps/details?id=${PLAY_APP_ID}&hl=iw`;
/** Google's official Hebrew badge, stored locally (CSP img-src 'self'). */
export const PLAY_BADGE_SRC = '/badges/google-play-he.png';

export const IOS_APP_URL = 'https://apps.apple.com/il/app/super-xxl/id6829450422';
/** Apple's official badges (Hebrew / English), stored locally like the Play badge. */
export const APP_STORE_BADGE_SRC = { he: '/badges/app-store-he.svg', en: '/badges/app-store-en.svg' } as const;

export const appStoreBadgeSrc = (lang: string) => (lang.startsWith('he') ? APP_STORE_BADGE_SRC.he : APP_STORE_BADGE_SRC.en);
