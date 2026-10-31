import { getI18n } from 'react-i18next';
import { errorCode } from '../../api';
import he from '../../i18n/promos.he.json';
import en from '../../i18n/promos.en.json';

/**
 * Shared bits of the מבצעים tab (SU11A-58). Its strings ship with this lazy
 * chunk (admin/i18n/promos.*.json, merged into admin.promos on load), not in the
 * shop's main bundle; scripts/check-i18n.js checks their parity.
 */
const i18n = getI18n();
i18n.addResourceBundle('he', 'translation', { admin: { promos: he } }, true, false);
i18n.addResourceBundle('en', 'translation', { admin: { promos: en } }, true, false);

export const K = 'admin.promos';

const ERRORS = ['promo_not_found', 'already_curated', 'pinned', 'hidden', 'pins_full', 'invalid_dates',
  'curation_not_found', 'reason_required', 'query_required'];

/** Toast text for a failed promo write. */
export function writeError(t: (k: string) => string, err: unknown): string {
  const code = errorCode(err);
  if (code === 'network') return t('admin.common.network');
  if (ERRORS.includes(code)) return t(`${K}.errors.${code}`);
  return t('admin.common.error');
}

/** <input type="datetime-local"> value (the admin's local time) -> ISO, or undefined. */
export function isoOrUndefined(local: string): string | undefined {
  if (!local) return undefined;
  const d = new Date(local);
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
}

export const INPUT = 'w-full min-h-[44px] px-3 rounded-xl border border-gray-300 bg-white text-base ' +
  'focus:outline-none focus:ring-2 focus:ring-emerald-600';
