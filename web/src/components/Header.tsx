import { ShoppingCart } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { applyDir } from '../i18n/config';

export default function Header() {
  const { t, i18n } = useTranslation();
  const isHe = i18n.language.startsWith('he');

  const toggleLang = () => {
    const next = isHe ? 'en' : 'he';
    i18n.changeLanguage(next);
    applyDir(next);
  };

  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShoppingCart className="text-emerald-600" size={22} />
          <span className="font-semibold text-gray-900 text-lg tracking-tight">
            {t('app.title')}
          </span>
        </div>
        <button
          onClick={toggleLang}
          className="text-sm font-medium text-gray-500 hover:text-emerald-600 transition-colors px-2 py-1 rounded"
          aria-label={t('header.aria_lang_toggle')}
        >
          {isHe ? t('language.switch_to_en') : t('language.switch_to_he')}
        </button>
      </div>
    </header>
  );
}
