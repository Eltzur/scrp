import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import Header from './components/Header';
import SearchBar from './components/SearchBar';
import Filters, { type FilterState } from './components/Filters';
import StatsBar from './components/StatsBar';
import ResultsList from './components/ResultsList';
import { useSearch, useCompare } from './api/hooks';

const DEFAULT_FILTERS: FilterState = { city: null, chain: null, compareMode: true };

function useActiveResults(query: string, filters: FilterState) {
  const city = filters.city ?? undefined;
  const chain = filters.chain ?? undefined;

  const search = useSearch(
    query,
    { city, chain },
    !filters.compareMode,
  );
  const compare = useCompare(
    query,
    { city },
    filters.compareMode,
  );

  return filters.compareMode ? compare : search;
}

export default function App() {
  const [query, setQuery] = useState('');
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const queryClient = useQueryClient();

  const { data, isLoading, isFetching, isError } = useActiveResults(query, filters);

  const handleSearch = useCallback((q: string) => setQuery(q), []);

  const handleRetry = () => {
    queryClient.invalidateQueries({ queryKey: [filters.compareMode ? 'compare' : 'search'] });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Header />

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-4">
        <SearchBar onSearch={handleSearch} />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <Filters filters={filters} onChange={setFilters} />
          <StatsBar />
        </div>

        <ResultsList
          result={data}
          isLoading={isLoading}
          isFetching={isFetching}
          isError={isError}
          query={query}
          onRetry={handleRetry}
        />
      </main>

      <footer className="max-w-6xl mx-auto px-4 py-6 border-t border-gray-200 mt-8">
        <p className="text-xs text-gray-400 text-center">
          Data sourced from Israeli government price transparency (gov.il), updated daily.
        </p>
      </footer>
    </div>
  );
}
