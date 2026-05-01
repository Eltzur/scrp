import { useCallback, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import XxlLogo from '../components/XxlLogo';
import SearchBar from '../components/SearchBar';
import Filters, { type FilterState } from '../components/Filters';
import StatsBar from '../components/StatsBar';
import ResultsList from '../components/ResultsList';
import { useSearch, useCompare } from '../api/hooks';
import { searchProducts, compareProducts } from '../api/client';
import type { ProductWithPrices } from '../api/client';

const DEFAULT_FILTERS: FilterState = {
  city:        null,
  chain:       null,
  compareMode: true,
  groupBy:     'chain',
};

const PAGE_SIZE = 30;

function useActiveResults(query: string, filters: FilterState) {
  const city    = filters.city  ?? undefined;
  const chain   = filters.chain ?? undefined;
  const groupBy = filters.groupBy;
  const search  = useSearch(query, { city, chain, group_by: groupBy }, !filters.compareMode);
  const compare = useCompare(query, { city }, filters.compareMode);
  return filters.compareMode ? compare : search;
}

export default function HomePage() {
  const { t, i18n }   = useTranslation();
  const lang          = i18n.language.startsWith('he') ? 'he' : 'en' as const;
  const [query,   setQuery]   = useState('');
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const queryClient           = useQueryClient();

  const [extraItems,  setExtraItems]  = useState<ProductWithPrices[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const [lastQuery,   setLastQuery]   = useState('');
  const [lastFilters, setLastFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [lastHasMore, setLastHasMore] = useState(false);

  const { data, isLoading, isFetching, isError } = useActiveResults(query, filters);

  const resetExtras = useCallback(() => {
    setExtraItems([]);
    setLoadingMore(false);
  }, []);

  const handleSearch = useCallback((q: string) => {
    setQuery(q);
    resetExtras();
    setLastQuery(q);
  }, [resetExtras]);

  const handleFiltersChange = useCallback((f: FilterState) => {
    setFilters(f);
    resetExtras();
    setLastFilters(f);
  }, [resetExtras]);

  const handleRetry = () => {
    queryClient.invalidateQueries({ queryKey: [filters.compareMode ? 'compare' : 'search'] });
  };

  const handleLoadMore = async () => {
    if (!data || loadingMore) return;
    const currentCount = data.items.length + extraItems.length;
    setLoadingMore(true);
    try {
      const opts = filters.compareMode
        ? { city: lastFilters.city ?? undefined, limit: PAGE_SIZE, offset: currentCount }
        : { city: lastFilters.city ?? undefined, chain: lastFilters.chain ?? undefined, group_by: lastFilters.groupBy, limit: PAGE_SIZE, offset: currentCount };
      const next = filters.compareMode
        ? await compareProducts(lastQuery, opts)
        : await searchProducts(lastQuery, opts);
      setExtraItems(prev => [...prev, ...next.items]);
      setLastHasMore(next.has_more);
    } finally {
      setLoadingMore(false);
    }
  };

  const mergedResult = data
    ? { ...data, items: [...data.items, ...extraItems], has_more: extraItems.length > 0 ? lastHasMore : (data.has_more ?? false) }
    : undefined;

  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-6xl mx-auto px-4 py-6 space-y-4">
        <section className="w-full py-8 md:py-12 flex justify-center">
          <XxlLogo variant="hero" lang={lang} className="w-full max-w-2xl" />
        </section>

        <SearchBar onSearch={handleSearch} />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <Filters filters={filters} onChange={handleFiltersChange} />
          <StatsBar />
        </div>

        <ResultsList
          result={mergedResult}
          isLoading={isLoading}
          isFetching={isFetching && !loadingMore}
          isError={isError}
          query={query}
          onRetry={handleRetry}
          onLoadMore={handleLoadMore}
          isLoadingMore={loadingMore}
        />
      </main>

      <footer className="max-w-6xl mx-auto px-4 py-6 border-t border-gray-200 mt-8">
        <p className="text-xs text-gray-400 text-center">
          {t('footer.attribution')}
        </p>
      </footer>
    </div>
  );
}
