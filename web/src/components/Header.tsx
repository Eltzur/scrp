import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ShoppingCart, User } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { applyDir } from '../i18n/config';
import { useBasket } from './BasketContext';
import { useAuth } from './AuthContext';
import XxlLogo from './XxlLogo';

export default function Header() {
  const { t, i18n }         = useTranslation();
  const { items, setIsOpen } = useBasket();
  const { user, signOut }   = useAuth();
  const navigate             = useNavigate();
  const isHe                 = i18n.language.startsWith('he');

  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef                     = useRef<HTMLDivElement>(null);

  const toggleLang = () => {
    const next = isHe ? 'en' : 'he';
    i18n.changeLanguage(next);
    applyDir(next);
  };

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleSignOut = async () => {
    setDropdownOpen(false);
    await signOut();
    navigate('/');
  };

  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 py-2 flex items-center justify-between">

        {/* Brand logo */}
        <Link to="/">
          <XxlLogo variant="header" lang={isHe ? 'he' : 'en'} className="h-12" />
        </Link>

        <div className="flex items-center gap-3">
          {/* Hot deals link */}
          <Link
            to="/promos"
            className="text-sm font-medium text-gray-600 hover:text-emerald-600 transition-colors hidden sm:inline"
          >
            🔥 מבצעים
          </Link>

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

          {/* Auth section */}
          {user ? (
            /* Logged in — account dropdown */
            <div className="relative" ref={dropdownRef}>
              <button
                onClick={() => setDropdownOpen(prev => !prev)}
                className="p-1.5 text-gray-500 hover:text-emerald-600 transition-colors"
                aria-label="תפריט חשבון"
              >
                <User size={20} />
              </button>

              {dropdownOpen && (
                <div className="absolute end-0 mt-1 w-52 bg-white rounded-xl border border-gray-200
                                shadow-lg py-1 z-50" dir="rtl">
                  <p className="px-4 py-2 text-xs text-gray-400 truncate border-b border-gray-100">
                    {user.email}
                  </p>
                  <Link
                    to="/baskets"
                    onClick={() => setDropdownOpen(false)}
                    className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                  >
                    הסלים שלי
                  </Link>
                  <Link
                    to="/favorites"
                    onClick={() => setDropdownOpen(false)}
                    className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 transition-colors"
                  >
                    המועדפים שלי
                  </Link>
                  <button
                    onClick={handleSignOut}
                    className="w-full text-start px-4 py-2 text-sm text-rose-600
                               hover:bg-rose-50 transition-colors"
                  >
                    התנתקות
                  </button>
                </div>
              )}
            </div>
          ) : (
            /* Logged out — login + signup links */
            <div className="flex items-center gap-2">
              <Link
                to="/login"
                className="text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors px-2 py-1"
              >
                התחברות
              </Link>
              <Link
                to="/signup"
                className="text-sm font-semibold text-white bg-emerald-600
                           hover:bg-emerald-700 transition-colors px-3 py-1.5 rounded-lg"
              >
                להרשמה
              </Link>
            </div>
          )}

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
