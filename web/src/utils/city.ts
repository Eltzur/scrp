/** Shared active-city resolution.
 *
 * Extracted from HomePage so the promos page defaults to the SAME city the user
 * is already searching in, rather than detecting one of its own — two pages
 * disagreeing about "your city" reads as a bug.
 *
 * Resolution order: last city the user picked (localStorage) → a fallback.
 * Synchronous: no page waits on it (SU11A-60 follow-up). The old IP lookup
 * (http://ip-api.com) was removed: browsers block it as mixed content on
 * https (SU11A-48 F-12), and where it hung instead of failing, the promos page
 * waited on it forever.
 */
import type { CityInfo } from '../api/client';

export const CITY_STORAGE_KEY = 'xxl_last_city';
export const FALLBACK_CITY    = 'תל אביב-יפו';

/** Best available fallback city from the loaded list. */
export function defaultCity(cities: CityInfo[]): string {
  return (
    cities.find(c => c.city === FALLBACK_CITY)?.city ??
    cities.find(c => c.city.includes('תל אביב'))?.city ??
    cities[0]?.city ??
    FALLBACK_CITY
  );
}

/** The city the user last chose, if it is still a known city. */
export function storedCity(cities: CityInfo[]): string | null {
  const saved = localStorage.getItem(CITY_STORAGE_KEY);
  return saved && cities.some(c => c.city === saved) ? saved : null;
}

/** Persist a single-city selection so the next visit skips geolocation. */
export function rememberCity(city: string): void {
  localStorage.setItem(CITY_STORAGE_KEY, city);
}

/** The remembered city before the city list has loaded (or when it fails):
 *  the stored value as is. '' when nothing is stored. */
export function rememberedCity(): string {
  try {
    return localStorage.getItem(CITY_STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}
