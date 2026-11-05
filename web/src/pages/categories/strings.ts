import { getI18n } from 'react-i18next';
import he from './strings.he.json';
import en from './strings.en.json';

/**
 * Strings of the category browse pages (SU11A-67). The page is a lazy chunk,
 * so its text ships with it, merged into `browse.*` on first import. Parity:
 * npm run test:i18n.
 */
const i18n = getI18n();
i18n.addResourceBundle('he', 'translation', { browse: he }, true, false);
i18n.addResourceBundle('en', 'translation', { browse: en }, true, false);

export const K = 'browse';
