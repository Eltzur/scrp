/**
 * Store links for the SUPER XXL mobile app (SU11A-53). One place for the web.
 *
 * IOS_APP_URL stays null until the iOS app is live on the App Store. Apple's
 * App Store badge and logo may only be used for an app that is available
 * there, so until then the site shows the text label "בקרוב גם ל-iPhone".
 * When the app goes live: set IOS_APP_URL, add Apple's official badge artwork
 * at APP_STORE_BADGE_SRC (unaltered, with its source noted in
 * public/badges/SOURCE.txt), and the label turns into that badge everywhere.
 */
export const PLAY_APP_ID = 'il.co.xxl.supermarket';
export const PLAY_STORE_URL = `https://play.google.com/store/apps/details?id=${PLAY_APP_ID}&hl=iw`;
/** Google's official Hebrew badge, stored locally (CSP img-src 'self'). */
export const PLAY_BADGE_SRC = '/badges/google-play-he.png';

export const IOS_APP_URL: string | null = null;
export const APP_STORE_BADGE_SRC = '/badges/app-store-he.svg';
