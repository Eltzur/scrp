import { useEffect, useRef, useState } from 'react';
import { Search, X, Clock } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useRecentSearches } from '../hooks/useRecentSearches';

interface Props {
  onSearch: (q: string) => void;
  initialValue?: string;
}

export default function SearchBar({ onSearch, initialValue = '' }: Props) {
  const { t } = useTranslation();
  const [value,    setValue]    = useState(initialValue);
  const [focused,  setFocused]  = useState(false);
  const timerRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef   = useRef<HTMLInputElement>(null);

  const { recentSearches, addSearch, removeSearch, clearAll } = useRecentSearches();

  // Debounced search + record to recent searches
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      onSearch(value);
      if (value.trim().length >= 2) addSearch(value.trim());
    }, 300);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  // addSearch is stable (no deps change), intentionally omitted from deps
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, onSearch]);

  const showDropdown = focused && value.trim() === '' && recentSearches.length > 0;

  const handleSelect = (q: string) => {
    setValue(q);
    onSearch(q);
    addSearch(q);
    inputRef.current?.focus();
  };

  // Delayed blur so clicks inside dropdown register before hiding
  const handleBlur = () => {
    setTimeout(() => setFocused(false), 150);
  };

  return (
    <div className="relative">
      <Search
        size={18}
        className="absolute start-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none"
      />
      <input
        ref={inputRef}
        type="text"
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => {
          if (e.key === 'Enter') {
            onSearch(value);
            if (value.trim().length >= 2) addSearch(value.trim());
          }
        }}
        onFocus={() => setFocused(true)}
        onBlur={handleBlur}
        placeholder={t('search.placeholder')}
        className="w-full ps-10 pe-10 py-3 border border-gray-300 rounded-xl text-gray-900
                   placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500
                   focus:border-transparent text-sm bg-white shadow-sm"
        autoFocus
        dir="auto"
      />
      {value && (
        <button
          onClick={() => { setValue(''); onSearch(''); }}
          className="absolute end-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-600"
          aria-label={t('search.clear')}
        >
          <X size={16} />
        </button>
      )}

      {/* Recent searches dropdown */}
      {showDropdown && (
        <div
          className="absolute top-full mt-1 inset-x-0 bg-white rounded-xl border border-gray-200
                     shadow-lg z-20 max-h-72 overflow-y-auto"
          dir="rtl"
        >
          <div className="px-4 py-2 border-b border-gray-100 flex items-center justify-between">
            <span className="text-xs font-medium text-gray-500">החיפושים האחרונים שלי</span>
            <button
              onMouseDown={e => e.preventDefault()} // keep dropdown open
              onClick={clearAll}
              className="text-xs text-gray-500 hover:text-rose-600 transition-colors"
            >
              נקה הכל
            </button>
          </div>

          <ul>
            {recentSearches.map(q => (
              <li key={q} className="flex items-center justify-between group px-4 py-2.5
                                      hover:bg-gray-50 transition-colors cursor-pointer">
                <button
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => handleSelect(q)}
                  className="flex items-center gap-2 flex-1 text-start text-sm text-gray-700"
                >
                  <Clock size={13} className="text-gray-500 shrink-0" />
                  <span dir="auto">{q}</span>
                </button>
                <button
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => removeSearch(q)}
                  className="p-1 text-gray-500 hover:text-gray-500 opacity-0 group-hover:opacity-100
                             transition-opacity"
                  aria-label="הסר חיפוש"
                >
                  <X size={12} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
