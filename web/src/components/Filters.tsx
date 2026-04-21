import { useChains, useCities } from '../api/hooks';
import { BarChart2 } from 'lucide-react';

export interface FilterState {
  city: string | null;
  chain: string | null;
  compareMode: boolean;
}

interface Props {
  filters: FilterState;
  onChange: (f: FilterState) => void;
}

export default function Filters({ filters, onChange }: Props) {
  const { data: cities = [] } = useCities();
  const { data: chains = [] } = useChains();

  return (
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
        Compare mode
      </button>

      {/* City filter */}
      <select
        value={filters.city ?? ''}
        onChange={e => onChange({ ...filters, city: e.target.value || null })}
        className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-700
                   bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
      >
        <option value="">All cities</option>
        {cities.map(c => (
          <option key={c} value={c}>{c}</option>
        ))}
      </select>

      {/* Chain filter — only shown when NOT in compare mode */}
      {!filters.compareMode && (
        <select
          value={filters.chain ?? ''}
          onChange={e => onChange({ ...filters, chain: e.target.value || null })}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm text-gray-700
                     bg-white focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <option value="">All chains</option>
          {chains.map(c => (
            <option key={c.chain_id} value={c.chain_id}>{c.name}</option>
          ))}
        </select>
      )}
    </div>
  );
}
