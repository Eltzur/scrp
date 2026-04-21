import { useEffect, useRef, useState } from 'react';
import { Search, X } from 'lucide-react';

interface Props {
  onSearch: (q: string) => void;
  initialValue?: string;
}

export default function SearchBar({ onSearch, initialValue = '' }: Props) {
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
        className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
      />
      <input
        type="text"
        value={value}
        onChange={e => setValue(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') onSearch(value); }}
        placeholder="Search products in Hebrew or English… e.g. במבה, milk, cottage"
        className="w-full pl-10 pr-10 py-3 border border-gray-300 rounded-xl text-gray-900
                   placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500
                   focus:border-transparent text-sm bg-white shadow-sm"
        autoFocus
      />
      {value && (
        <button
          onClick={() => { setValue(''); onSearch(''); }}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          aria-label="Clear"
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
}
