import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import XxlLogo from '../components/XxlLogo';
import SearchBar from '../components/SearchBar';
import Filters, { type FilterState } from '../components/Filters';
import StatsBar from '../components/StatsBar';
import FreshnessStrip from '../components/FreshnessStrip';
import ResultsList from '../components/ResultsList';
import ProductDetailModal from '../components/ProductDetailModal';
import AppBadges from '../components/AppBadges';
import { useSearch, useCompare } from '../api/hooks';
import { searchProducts, compareProducts, getProduct, isBusyError } from '../api/client';
import type { ProductWithPrices, CityInfo } from '../api/client';
import { defaultCity, matchIpCity, rememberCity, storedCity } from '../utils/city';

const DEFAULT_FILTERS: FilterState = {
  city:        null,
  chain:       null,
  compareMode: true,
  groupBy:     'chain',
};

// City resolution lives in utils/city so PromosPage defaults to the same city
// this page is searching in. Behaviour here is unchanged.

// SU11A-47: 20 (was 30, the server default): a smaller first page answers
// sooner and fills the first screen at every width; load-more pages are 20 too.
const PAGE_SIZE = 20;

/**
 * Identity of a result row for the load-more dedupe. group_by=store returns one
 * row per store, so the same item_code legitimately repeats there.
 */
function rowKey(item: ProductWithPrices, groupBy: FilterState['groupBy']): string {
  if (groupBy !== 'store') return item.product.item_code;
  const q = item.quotes[0];
  return `${item.product.item_code}|${q?.chain_id ?? ''}|${q?.store_id ?? ''}`;
}

function useActiveResults(query: string, filters: FilterState) {
  const city    = filters.city?.length  ? filters.city  : undefined;
  const chain   = filters.chain?.length ? filters.chain : undefined;
  const groupBy = filters.groupBy;
  const search  = useSearch(query, { city, chain, group_by: groupBy, limit: PAGE_SIZE }, !filters.compareMode);
  const compare = useCompare(query, { city, limit: PAGE_SIZE }, filters.compareMode);
  return filters.compareMode ? compare : search;
}

export default function HomePage({ cities }: { cities: CityInfo[] }) {
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
  // True once a load-more has finished, so has_more comes from the last page
  // even when that page added nothing (extraItems.length alone can't tell).
  const [loadedMore,  setLoadedMore]  = useState(false);
  // Next request offset = rows the server has handed out, NOT rows rendered:
  // the dedupe below can drop rows (SU11A-46; mirrors mobile SU10M-3). Search
  // v2 pages on its own table and can skip an item, so a page may overlap the
  // previous one (SU11A-45 finding 9b). null = start after the first page.
  const nextOffset = useRef<number | null>(null);
  // A product picked from the search box suggestions (SU11A-47).
  const [modalItem, setModalItem] = useState<ProductWithPrices | null>(null);

  // Detect city once — fires when the cities list first populates.
  // Guarded by ref so React strict-mode double-invocation doesn't double-detect.
  const cityDetected = useRef(false);
  useEffect(() => {
    if (cityDetected.current || cities.length === 0) return;
    cityDetected.current = true;

    // 1. Prefer the city the user last used.
    const saved = storedCity(cities);
    if (saved) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- applies the saved city once the city list arrives
      setFilters(f => ({ ...f, city: [saved] }));
      return;
    }

    // 2. Try IP geolocation (free, no key, Hebrew city names).
    fetch('http://ip-api.com/json/?fields=city&lang=he')
      .then(r => r.json())
      .then((json: { city?: string }) => {
        const matched = matchIpCity(json.city ?? '', cities);
        setFilters(f => ({ ...f, city: [matched ?? defaultCity(cities)] }));
      })
      .catch(() => {
        setFilters(f => ({ ...f, city: [defaultCity(cities)] }));
      });
  }, [cities]);

  // Persist single-city selections to localStorage so next visit skips geolocation.
  useEffect(() => {
    if (filters.city?.length === 1) {
      rememberCity(filters.city[0]);
    }
  }, [filters.city]);

  const { data, isLoading, isFetching, isError, error } = useActiveResults(query, filters);

  const resetExtras = useCallback(() => {
    setExtraItems([]);
    setLoadingMore(false);
    setLoadedMore(false);
    nextOffset.current = null;
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

  const handleOpenProduct = useCallback(async (itemCode: string) => {
    try {
      setModalItem(await getProduct(itemCode));
      return true;
    } catch {
      return false;   // the search box then searches the product's name instead
    }
  }, []);

  const handleRetry = () => {
    queryClient.invalidateQueries({ queryKey: [filters.compareMode ? 'compare' : 'search'] });
  };

  const handleLoadMore = async () => {
    if (!data || loadingMore) return;
    setLoadingMore(true);
    try {
      const city    = lastFilters.city?.length  ? lastFilters.city  : undefined;
      const chain   = lastFilters.chain?.length ? lastFilters.chain : undefined;
      const groupBy = filters.compareMode ? 'chain' : lastFilters.groupBy;
      const fetchPage = (offset: number) => filters.compareMode
        ? compareProducts(lastQuery, { city, limit: PAGE_SIZE, offset })
        : searchProducts(lastQuery, { city, chain, group_by: lastFilters.groupBy, limit: PAGE_SIZE, offset });

      const seen = new Set([...data.items, ...extraItems].map(it => rowKey(it, groupBy)));
      let offset = nextOffset.current ?? data.items.length;
      let next   = await fetchPage(offset);
      // An empty page cannot advance the offset by its own length, so step a
      // full page past it.
      offset += next.items.length || PAGE_SIZE;
      let fresh  = next.items.filter(it => !seen.has(rowKey(it, groupBy)));
      if (fresh.length === 0 && next.has_more) {
        // Nothing new but the server says there is more: try one more page, then stop.
        next   = await fetchPage(offset);
        offset += next.items.length || PAGE_SIZE;
        fresh  = next.items.filter(it => !seen.has(rowKey(it, groupBy)));
      }
      nextOffset.current = offset;
      setExtraItems(prev => [...prev, ...fresh]);
      setLastHasMore(fresh.length > 0 && next.has_more);
      setLoadedMore(true);
    } finally {
      setLoadingMore(false);
    }
  };

  const mergedResult = data
    ? { ...data, items: [...data.items, ...extraItems], has_more: loadedMore ? lastHasMore : (data.has_more ?? false) }
    : undefined;

  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-6xl mx-auto px-4 pt-6 pb-24 space-y-4">
        <section className="w-full py-8 md:py-12 flex justify-center">
          <XxlLogo variant="hero" lang={lang} className="w-full max-w-2xl" />
        </section>

        <SearchBar onSearch={handleSearch} onOpenProduct={handleOpenProduct} />

        {/* SU11A-53: the app section, on the start screen only (results take its place) */}
        {!query && (
          <section aria-labelledby="app-section-title" className="text-center py-3">
            <h2 id="app-section-title" className="text-lg font-bold text-[#022C22]">{t('apps.section_title')}</h2>
            <p className="text-sm text-gray-600 mt-1">{t('apps.section_sub')}</p>
            <AppBadges size="md" className="mt-3" />
          </section>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <Filters filters={filters} onChange={handleFiltersChange} cities={cities} />
          <StatsBar />
        </div>

        <FreshnessStrip />

        <ResultsList
          result={mergedResult}
          isLoading={isLoading}
          isFetching={isFetching && !loadingMore}
          isError={isError}
          isBusy={isBusyError(error)}
          query={query}
          onRetry={handleRetry}
          onLoadMore={handleLoadMore}
          isLoadingMore={loadingMore}
        />
      </main>

      {modalItem && <ProductDetailModal item={modalItem} onClose={() => setModalItem(null)} />}

      <footer className="max-w-6xl mx-auto px-4 py-6 border-t border-gray-200 mt-8">
        <p className="text-xs text-gray-500 text-center">
          {t('footer.attribution')}
        </p>
      </footer>
    </div>
  );
}
