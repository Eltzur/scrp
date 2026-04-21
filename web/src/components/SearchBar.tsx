import { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Props {
  onSearch: (q: string) => void;
  initialValue?: string;
}

export default function SearchBar({ onSearch, initialValue = '' }: Props) {
  const { t } = useTranslation();
  const [value, setValue] = useState(initialValue);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => onSearch(value), 300);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [value, onSearch]);

  return (
    <div className="relative">
      <Search
        size={18}
        className="absolute start-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
      />
      <input
        type="text"
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') onSearch(value); }}
        placeholder={t('search.placeholder')}
        className="w-full ps-10 pe-10 py-3 border border-gray-300 rounded-xl text-gray-900
                   placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500
                   focus:border-transparent text-sm bg-white shadow-sm"
        autoFocus
        dir="auto"
      />
      {value && (
        <button
          onClick={() => { setValue(''); onSearch(''); }}
          className="absolute end-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          aria-label={t('search.clear')}
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
}
