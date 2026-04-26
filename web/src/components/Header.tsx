import { ShoppingCart } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { applyDir } from '../i18n/config';
import { useBasket } from './BasketContext';

export default function Header() {
  const { t, i18n } = useTranslation();
  const { items, setIsOpen } = useBasket();
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

        <div className="flex items-center gap-3">
          {/* Basket icon with badge */}
          <button
            onClick={() => setIsOpen(true)}
            className="relative p-1.5 text-gray-500 hover:text-emerald-600 transition-colors"
            aria-label="פתח סל קניות"
          >
            <ShoppingCart size={20} />
            {items.length > 0 && (
              <span className="absolute -top-0.5 -end-0.5 min-w-[18px] h-[18px] px-0.5
                               bg-emerald-500 text-white text-[10px] font-bold rounded-full
                               flex items-center justify-center leading-none">
                {items.length > 99 ? '99+' : items.length}
              </span>
            )}
          </button>

          {/* Language toggle */}
          <button
            onClick={toggleLang}
            className="text-sm font-medium text-gray-500 hover:text-emerald-600 transition-colors px-2 py-1 rounded"
            aria-label={t('header.aria_lang_toggle')}
          >
            {isHe ? t('language.switch_to_en') : t('language.switch_to_he')}
          </button>
        </div>
      </div>
    </header>
  );
}
