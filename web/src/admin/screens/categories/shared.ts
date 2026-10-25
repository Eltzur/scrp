import { useQuery } from '@tanstack/react-query';
import { getI18n } from 'react-i18next';
import { errorCode, getCategoryTreeA } from '../../api';
import he from '../../i18n/categories.he.json';
import en from '../../i18n/categories.en.json';

/**
 * Shared bits of the קטגוריות tab (SU11A-57). Its strings ship with this lazy
 * chunk (admin/i18n/categories.*.json, merged into admin.categories on load),
 * not in the shop's main bundle; scripts/check-i18n.js checks their parity.
 */
const i18n = getI18n();
i18n.addResourceBundle('he', 'translation', { admin: { categories: he } }, true, false);
i18n.addResourceBundle('en', 'translation', { admin: { categories: en } }, true, false);

export const K = 'admin.categories';

export function useTree() {
  return useQuery({ queryKey: ['admin', 'category-tree'], queryFn: getCategoryTreeA, staleTime: 60 * 60 * 1000, retry: 1 });
}

/** Toast text for a failed category write. */
export function writeError(t: (k: string) => string, err: unknown): string {
  const code = errorCode(err);
  if (code === 'network') return t('admin.common.network');
  if (['changed_since', 'not_revertible', 'invalid_category'].includes(code)) return t(`${K}.item.${code}`);
  if (code === 'item_not_found' || code === 'http_404') return t(`${K}.item.not_found`);
  return t('admin.common.error');
}
