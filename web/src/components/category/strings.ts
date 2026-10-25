import { getI18n } from 'react-i18next';
import he from './strings.he.json';
import en from './strings.en.json';

/**
 * Strings of the category picker and the suggestion dialog (SU11A-57). Both are
 * lazy chunks, so their text ships with them, merged into `category.*` on
 * first import, instead of in the shop's main bundle. The few strings the
 * always-loaded CategoryLine needs stay in src/i18n/locales. Parity: npm run test:i18n.
 */
const i18n = getI18n();
i18n.addResourceBundle('he', 'translation', { category: he }, true, false);
i18n.addResourceBundle('en', 'translation', { category: en }, true, false);
