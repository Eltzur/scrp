import { useRef, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { BarChart2, ChevronDown } from 'lucide-react';
import { useChains } from '../api/hooks';
import type { CityInfo } from '../api/client';

export interface FilterState {
  city: string[] | null;
  chain: string[] | null;
  compareMode: boolean;
  groupBy: 'chain' | 'store';
}

interface MultiSelectProps {
  options: { value: string; label: string }[];
  selected: string[] | null;
  onChange: (vals: string[] | null) => void;
  placeholder: string;
  disabled?: boolean;
}

function MultiSelect({ options, selected, onChange, placeholder, disabled = false }: MultiSelectProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const sel = selected ?? [];

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Clear on both edges of the transition, so a dropdown never reopens showing
  // the previous session's query (and its filtered subset) as if it were the
  // full list.
  useEffect(() => { setQuery(''); }, [open]);

  // localeCompare-style folding is unnecessary here: Hebrew has no case, and
  // toLowerCase covers the Latin-script chain names.
  const q = query.trim().toLowerCase();
  const filtered = q
    ? options.filter(o => o.label.toLowerCase().includes(q))
    : options;

  const toggle = (val: string) => {
    const next = sel.includes(val) ? sel.filter(v => v !== val) : [...sel, val];
    onChange(next.length ? next : null);
  };

  const buttonLabel = sel.length === 0
    ? placeholder
    : sel.length === 1 ? sel[0] : `${sel.length} נבחרו`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => !disabled && setOpen(o => !o)}
        className={`flex items-center gap-1.5 px-3 py-1.5 border border-gray-300 rounded-lg
                   text-sm text-gray-700 bg-white whitespace-nowrap
                   ${disabled
                     ? 'opacity-40 cursor-not-allowed'
                     : 'hover:border-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 cursor-pointer'}`}
      >
        <span>{buttonLabel}</span>
        <ChevronDown size={13} className={`text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div
          className="absolute top-full mt-1 z-30 bg-white border border-gray-200 rounded-xl shadow-lg
                     min-w-[180px] max-h-72 flex flex-col"
          dir="rtl"
        >
          <div className="px-2 pt-2 pb-1 border-b border-gray-100 shrink-0">
            <input
              type="text"
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder={t('filters.search_placeholder')}
              className="w-full px-2 py-1 border border-gray-300 rounded-lg text-sm text-gray-700
                         placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <div className="flex items-center justify-between px-3 py-2 border-b border-gray-100 shrink-0">
            <button
              onMouseDown={e => e.preventDefault()}
              // Union with the existing selection rather than replacing it, and
              // only over what the query currently shows — that is what makes
              // repeated filter-then-select-all accumulate instead of clobber.
              onClick={() => {
                const merged = Array.from(new Set([...sel, ...filtered.map(o => o.value)]));
                onChange(merged.length ? merged : null);
              }}
              className="text-xs text-emerald-700 hover:text-emerald-800 font-medium"
            >
              בחר הכל
            </button>
            <button
              onMouseDown={e => e.preventDefault()}
              onClick={() => onChange(null)}
              className="text-xs text-gray-500 hover:text-rose-600"
            >
              נקה הכל
            </button>
          </div>
          <ul className="overflow-y-auto">
            {filtered.map(o => (
              <li key={o.value}>
                <label className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer text-sm text-gray-700">
                  <input
                    type="checkbox"
                    checked={sel.includes(o.value)}
                    onChange={() => toggle(o.value)}
                    className="accent-emerald-600 w-3.5 h-3.5 shrink-0"
                  />
                  <span>{o.label}</span>
                </label>
              </li>
            ))}
            {filtered.length === 0 && (
              <li className="px-3 py-2 text-sm text-gray-500">
                {t('filters.no_results')}
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

interface Props {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  cities: CityInfo[];
}

export default function Filters({ filters, onChange, cities }: Props) {
  const { t } = useTranslation();
  const { data: chains = [] } = useChains();

  const selectedCities = cities.filter((c: CityInfo) => (filters.city ?? []).includes(c.city));
  const cityHasLowCoverage =
    filters.compareMode &&
    selectedCities.length > 0 &&
    selectedCities.every((c: CityInfo) => c.chain_count < 2);

  const cityOptions = [...cities]
    .sort((a: CityInfo, b: CityInfo) => a.city.localeCompare(b.city, 'he'))
    .map((c: CityInfo) => ({
      value: c.city,
      label: t('filters.city_option', { city: c.city, chains: c.chain_count }),
    }));

  const chainOptions = chains.map(c => ({ value: c.chain_id, label: c.name }));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-3 items-center">
        {/* Compare mode toggle */}
        <button
          onClick={() => onChange({ ...filters, compareMode: !filters.compareMode })}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors
            ${filters.compareMode
              ? 'bg-emerald-700 text-white border-emerald-600'
              : 'bg-white text-gray-600 border-gray-300 hover:border-emerald-400'}`}
        >
          <BarChart2 size={14} />
          {t('filters.compare_mode')}
        </button>

        {/* City multi-select */}
        <MultiSelect
          options={cityOptions}
          selected={filters.city}
          onChange={city => onChange({ ...filters, city })}
          placeholder={t('filters.all_cities')}
        />

        {/* Chain multi-select — disabled in compare mode */}
        <MultiSelect
          options={chainOptions}
          selected={filters.chain}
          onChange={chain => onChange({ ...filters, chain })}
          placeholder={t('filters.all_chains')}
        />

        {/* Group by — disabled in compare mode */}
        <div className={`flex items-center gap-1.5 ${filters.compareMode ? 'opacity-40 cursor-not-allowed' : ''}`}>
          <span className="text-xs text-gray-500">{t('filters.group_by')}:</span>
          {(['chain', 'store'] as const).map(mode => (
            <button
              key={mode}
              disabled={filters.compareMode}
              onClick={() => onChange({ ...filters, groupBy: mode })}
              className={`px-2.5 py-1 rounded text-xs font-medium border transition-colors
                ${filters.groupBy === mode
                  ? 'bg-gray-800 text-white border-gray-800'
                  : 'bg-white text-gray-500 border-gray-300 hover:border-gray-400'}
                ${filters.compareMode ? 'cursor-not-allowed' : ''}`}
            >
              {t(`filters.group_${mode}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Low-coverage city warning */}
      {cityHasLowCoverage && (
        <div className="flex items-center justify-between gap-3 text-xs bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          <span className="text-amber-700">
            {t('filters.compare_disabled_city', {
              city: selectedCities[0].city,
              chain_name: selectedCities[0].city,
            })}
          </span>
          <button
            onClick={() => onChange({ ...filters, compareMode: false })}
            className="shrink-0 text-amber-800 font-semibold underline hover:text-amber-950 transition-colors"
          >
            {t('filters.compare_off')}
          </button>
        </div>
      )}
    </div>
  );
}
