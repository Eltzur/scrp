import { getI18n } from 'react-i18next';
import he from './strings.he.json';
import en from './strings.en.json';

/**
 * Strings of the result view modes (SU11A-72). The switcher and the list /
 * table views are lazy chunks, so their text ships with them, merged into
 * `views.*` on first import. Parity: npm run test:i18n.
 */
const i18n = getI18n();
i18n.addResourceBundle('he', 'translation', { views: he }, true, false);
i18n.addResourceBundle('en', 'translation', { views: en }, true, false);

export const K = 'views';
