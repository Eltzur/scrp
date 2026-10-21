import { useEffect, useId, useRef, useState } from 'react';
import { Search, X, Clock, Package, Tag } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useRecentSearches } from '../hooks/useRecentSearches';
import { getSuggestions, type Suggestion } from '../api/client';

interface Props {
  onSearch: (q: string) => void;
  /** A product suggestion was chosen. Resolve false when it could not be opened; the text is then searched. */
  onOpenProduct?: (itemCode: string) => Promise<boolean>;
  initialValue?: string;
}

/** Search requests wait for a pause this long (SU11A-47: was 300). */
const SEARCH_DEBOUNCE_MS = 200;
/** /suggest is cheap and cached server-side, so it can follow typing closer. */
const SUGGEST_DEBOUNCE_MS = 160;
const SUGGEST_LIMIT = 8;

type Option =
  | { type: 'recent'; text: string }
  | { type: 'suggestion'; s: Suggestion };

/**
 * Search box as a WAI-ARIA combobox (SU11A-47): the input owns a listbox of
 * suggestions from /suggest while typing, or the recent searches when empty.
 * Arrow keys move the active option (aria-activedescendant; focus stays in the
 * input), Enter picks it (or searches the typed text when none is active),
 * Escape closes the list.
 */
export default function SearchBar({ onSearch, onOpenProduct, initialValue = '' }: Props) {
  const { t } = useTranslation();
  const [value,       setValue]       = useState(initialValue);
  const [focused,     setFocused]     = useState(false);
  const [dismissed,   setDismissed]   = useState(false);
  const [suggestions, setSuggestions] = useState<{ q: string; items: Suggestion[] }>({ q: '', items: [] });
  const [active,      setActive]      = useState(-1);
  const timerRef   = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef   = useRef<HTMLInputElement>(null);
  const listId     = useId();

  const { recentSearches, addSearch, removeSearch, clearAll } = useRecentSearches();

  // Debounced search + record to recent searches
  useEffect(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      onSearch(value);
      if (value.trim().length >= 2) addSearch(value.trim());
    }, SEARCH_DEBOUNCE_MS);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  // addSearch is stable (no deps change), intentionally omitted from deps
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, onSearch]);

  // Suggestions: debounced, and the previous request is aborted, so a late
  // answer for an older prefix can never replace a newer one.
  useEffect(() => {
    const q = value.trim();
    if (!q) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      getSuggestions(q, SUGGEST_LIMIT, controller.signal)
        .then(res => setSuggestions({ q, items: res.items }))
        .catch(() => { /* aborted, or offline: keep what is shown; the search still runs */ });
    }, SUGGEST_DEBOUNCE_MS);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [value]);

  const trimmed = value.trim();
  const options: Option[] = trimmed === ''
    ? recentSearches.map(text => ({ type: 'recent' as const, text }))
    // Suggestions for an older prefix stay up until the new ones arrive (no flicker).
    : suggestions.q ? suggestions.items.map(s => ({ type: 'suggestion' as const, s })) : [];
  const open = focused && !dismissed && options.length > 0;
  const activeIndex = open && active < options.length ? active : -1;
  const optionId = (i: number) => `${listId}-opt-${i}`;

  const runSearch = (q: string) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setValue(q);
    onSearch(q);
    if (q.trim().length >= 2) addSearch(q.trim());
  };

  const choose = async (opt: Option) => {
    setDismissed(true);
    setActive(-1);
    if (opt.type === 'recent') {
      runSearch(opt.text);
    } else if (opt.s.kind === 'product' && opt.s.item_code && onOpenProduct) {
      const opened = await onOpenProduct(opt.s.item_code);
      if (!opened) runSearch(opt.s.text);
    } else {
      runSearch(opt.s.text);
    }
    inputRef.current?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      if (!options.length) return;
      e.preventDefault();
      if (!open) {
        setDismissed(false);
        setActive(e.key === 'ArrowDown' ? 0 : options.length - 1);
        return;
      }
      // -1 is the input itself: past the last option goes back to it, and
      // up from it wraps to the last option.
      const next = activeIndex + (e.key === 'ArrowDown' ? 1 : -1);
      setActive(next >= options.length ? -1 : next < -1 ? options.length - 1 : next);
    } else if (e.key === 'Enter') {
      if (activeIndex >= 0) {
        e.preventDefault();
        void choose(options[activeIndex]);
      } else {
        setDismissed(true);
        runSearch(value);
      }
    } else if (e.key === 'Escape') {
      if (open) {
        e.preventDefault();
        setDismissed(true);
        setActive(-1);
      }
    }
  };

  // Delayed blur so clicks inside dropdown register before hiding
  const handleBlur = () => {
    setTimeout(() => { setFocused(false); setActive(-1); }, 150);
  };

  const kindLabel = (s: Suggestion) =>
    s.kind === 'product' ? t('search.suggest_kind_product')
      : s.kind === 'brand' ? t('search.suggest_kind_brand') : t('search.suggest_kind_term');

  return (
    <div className="relative">
      <Search
        size={18}
        className="absolute start-3 top-1/2 -translate-y-1/2 text-gray-500 pointer-events-none"
        aria-hidden="true"
      />
      <input
        ref={inputRef}
        type="text"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={activeIndex >= 0 ? optionId(activeIndex) : undefined}
        aria-label={t('search.placeholder')}
        value={value}
        onChange={e => { setValue(e.target.value); setDismissed(false); setActive(-1); }}
        onKeyDown={onKeyDown}
        onFocus={() => setFocused(true)}
        onBlur={handleBlur}
        placeholder={t('search.placeholder')}
        className="w-full ps-10 pe-10 py-3 border border-gray-300 rounded-xl text-gray-900
                   placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500
                   focus:border-transparent text-sm bg-white shadow-sm"
        autoFocus
        autoComplete="off"
        dir="auto"
      />
      {value && (
        <button
          onClick={() => { setValue(''); onSearch(''); setDismissed(false); inputRef.current?.focus(); }}
          className="absolute end-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700 rounded
                     focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          aria-label={t('search.clear')}
        >
          <X size={16} />
        </button>
      )}

      {/* Suggestions while typing, recent searches when empty: one listbox. */}
      <div
        className={open
          ? 'absolute top-full mt-1 inset-x-0 bg-white rounded-xl border border-gray-200 shadow-lg z-20 max-h-80 overflow-y-auto'
          : 'hidden'}
        dir="rtl"
      >
        {open && trimmed === '' && (
          <div className="px-4 py-2 border-b border-gray-100 flex items-center justify-between">
            <span className="text-xs font-medium text-gray-600">{t('search.recent_title')}</span>
            <button
              onMouseDown={e => e.preventDefault()} // keep dropdown open
              onClick={clearAll}
              tabIndex={-1}
              className="text-xs text-gray-600 hover:text-rose-700 transition-colors"
            >
              {t('search.recent_clear_all')}
            </button>
          </div>
        )}
        <ul id={listId} role="listbox" aria-label={trimmed === '' ? t('search.recent_title') : t('search.suggestions_label')}>
          {open && options.map((opt, i) => {
            const isActive = i === activeIndex;
            const text = opt.type === 'recent' ? opt.text : opt.s.text;
            return (
              <li
                key={`${opt.type}-${opt.type === 'suggestion' ? opt.s.kind + (opt.s.item_code ?? '') : ''}-${text}`}
                id={optionId(i)}
                role="option"
                aria-selected={isActive}
                onMouseDown={e => e.preventDefault()}
                onClick={() => void choose(opt)}
                onMouseEnter={() => setActive(i)}
                className={`flex items-center justify-between gap-2 px-4 py-2.5 min-h-11 cursor-pointer text-sm text-gray-900
                            ${isActive ? 'bg-emerald-50 outline outline-2 -outline-offset-2 outline-emerald-600' : 'hover:bg-gray-50'}`}
              >
                <span className="flex items-center gap-2 min-w-0">
                  {opt.type === 'recent'
                    ? <Clock size={13} className="text-gray-500 shrink-0" aria-hidden="true" />
                    : opt.s.kind === 'product'
                      ? <Package size={14} className="text-emerald-700 shrink-0" aria-hidden="true" />
                      : opt.s.kind === 'brand'
                        ? <Tag size={14} className="text-emerald-700 shrink-0" aria-hidden="true" />
                        : <Search size={14} className="text-gray-500 shrink-0" aria-hidden="true" />}
                  <span dir="auto" className="truncate">{text}</span>
                </span>
                {opt.type === 'recent' ? (
                  <button
                    onMouseDown={e => e.preventDefault()}
                    onClick={e => { e.stopPropagation(); removeSearch(opt.text); }}
                    tabIndex={-1}
                    className="p-1 text-gray-500 hover:text-gray-700"
                    aria-label={t('search.recent_remove')}
                  >
                    <X size={12} />
                  </button>
                ) : (
                  <span className="text-xs text-gray-600 shrink-0">{kindLabel(opt.s)}</span>
                )}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
