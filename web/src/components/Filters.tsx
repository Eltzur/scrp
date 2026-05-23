import { useTranslation } from 'react-i18next';
import { BarChart2 } from 'lucide-react';
import { useChains, useCities } from '../api/hooks';
import type { CityInfo } from '../api/client';

export interface FilterState {
  city: string | null;
  chain: string | null;
  compareMode: boolean;
  groupBy: 'chain' | 'store';
}

interface Props {
  filters: FilterState;
  onChange: (f: FilterState) => void;
}

export default function Filters({ filters, onChange }: Props) {
  const { t } = useTranslation();
  const { data: cities = [] } = useCities();
  const { data: chains = [] } = useChains();

  const selectedCity = cities.find((c: CityInfo) => c.city === filters.city);
  const cityHasLowCoverage = !!selectedCity && selectedCity.chain_count < 2;
  const chainName =
    chains.find(c => c.chain_id === selectedCity?.chain_ids?.[0])?.name ??
    selectedCity?.city ??
    '';

  const disabledClass = 'opacity-40 cursor-not-allowed';

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-3 items-center">
        {/* Compare mode toggle */}
        <button
          onClick={() => onChange({ ...filters, compareMode: !filters.compareMode })}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors
            ${filters.compareMode
              ? 'bg-emerald-600 text-white border-emerald-600'
              : 'bg-white text-gray-600 border-gray-300 hover:border-emerald-400'}`}
        >
          <BarChart2 size={14} />
          {t('filters.compare_mode')}
        </button>

        {/* City filter */}
        <select
          value={filters.city ?? ''}
          onChange={e => onChange({ ...filters, city: e.target.value || null })}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-700
                     bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <option value="">{t('filters.all_cities')}</option>
          {[...cities]
            .sort((a: CityInfo, b: CityInfo) => a.city.localeCompare(b.city, 'he'))
            .map((c: CityInfo) => (
              <option key={c.city} value={c.city}>
                {t('filters.city_option', { city: c.city, chains: c.chain_count })}
              </option>
            ))}
        </select>

        {/* Chain filter — disabled in compare mode */}
        <select
          value={filters.chain ?? ''}
          disabled={filters.compareMode}
          onChange={e => onChange({ ...filters, chain: e.target.value || null })}
          className={`px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-700
                     bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500
                     ${filters.compareMode ? disabledClass : ''}`}
        >
          <option value="">{t('filters.all_chains')}</option>
          {chains.map(c => (
            <option key={c.chain_id} value={c.chain_id}>{c.name}</option>
          ))}
        </select>

        {/* Group by — disabled in compare mode */}
        <div className={`flex items-center gap-1.5 ${filters.compareMode ? disabledClass : ''}`}>
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
      {filters.compareMode && cityHasLowCoverage && selectedCity && (
        <div className="flex items-center justify-between gap-3 text-xs bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          <span className="text-amber-700">
            {t('filters.compare_disabled_city', {
              city: selectedCity.city,
              chain_name: chainName,
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
