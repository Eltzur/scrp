import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import en from './locales/en.json';
import he from './locales/he.json';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, he: { translation: he } },
    fallbackLng: 'he',
    detection: {
      order: ['localStorage'],
      caches: ['localStorage'],
      lookupLocalStorage: 'lang',
    },
    interpolation: { escapeValue: false },
  });

export function applyDir(lang: string) {
  const dir = lang === 'he' ? 'rtl' : 'ltr';
  document.documentElement.dir = dir;
  document.documentElement.lang = lang;
}

// Apply on first load
applyDir(i18n.language.startsWith('he') ? 'he' : 'en');

export default i18n;
