/** Shared active-city resolution.
 *
 * Extracted from HomePage so the promos page defaults to the SAME city the user
 * is already searching in, rather than detecting one of its own — two pages
 * disagreeing about "your city" reads as a bug.
 *
 * Resolution order: last city the user picked (localStorage) → IP geolocation →
 * a sensible fallback from the loaded list.
 */
import type { CityInfo } from '../api/client';

export const CITY_STORAGE_KEY = 'xxl_last_city';
export const FALLBACK_CITY    = 'תל אביב-יפו';

/** Match an IP-returned city name against our canonical city list. */
export function matchIpCity(ipCity: string, cities: CityInfo[]): string | null {
  const s = ipCity.trim();
  if (!s) return null;
  return (
    cities.find(c => c.city === s)?.city ??
    // e.g. IP returns "תל אביב", DB has "תל אביב-יפו"
    cities.find(c => c.city.startsWith(s))?.city ??
    // e.g. IP returns a long variant that starts with the DB canonical
    cities.find(c => s.startsWith(c.city))?.city ??
    null
  );
}

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

/** Resolve the active city: stored → IP geolocation → fallback. Never rejects. */
export function detectCity(cities: CityInfo[]): Promise<string> {
  const saved = storedCity(cities);
  if (saved) return Promise.resolve(saved);

  return fetch('http://ip-api.com/json/?fields=city&lang=he')
    .then(r => r.json())
    .then((json: { city?: string }) => matchIpCity(json.city ?? '', cities) ?? defaultCity(cities))
    .catch(() => defaultCity(cities));
}
