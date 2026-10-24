/** Mobile platform from the user agent, for the app banner (SU11A-53). */
export type AppPlatform = 'android' | 'ios' | 'desktop';

export function detectPlatform(ua: string, maxTouchPoints = 0): AppPlatform {
  if (/android/i.test(ua)) return 'android';
  if (/iphone|ipad|ipod/i.test(ua)) return 'ios';
  // iPadOS 13+ reports a desktop Mac user agent; touch support gives it away.
  if (/macintosh/i.test(ua) && maxTouchPoints > 1) return 'ios';
  return 'desktop';
}
