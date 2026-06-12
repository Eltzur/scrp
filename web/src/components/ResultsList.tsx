import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { SearchResult, PromoItem } from '../api/client';
import { getPromosBulk } from '../api/client';
import ProductCard from './ProductCard';
import ProductCardSkeleton from './ProductCardSkeleton';
import EmptyState from './EmptyState';
import ErrorState from './ErrorState';
import { Loader2 } from 'lucide-react';

interface Props {
  result: SearchResult | undefined;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  query: string;
  onRetry: () => void;
  onLoadMore?: () => void;
  isLoadingMore?: boolean;
}

export type PromoMap = Map<string, PromoItem[]>;

const SKELETON_COUNT = 6;

export default function ResultsList({
  result, isLoading, isFetching, isError, query, onRetry, onLoadMore, isLoadingMore,
}: Props) {
  const { t } = useTranslation();

  // promosByStore is populated lazily AFTER results render — never blocks first paint.
  // Old promos stay visible during search transitions (stale-while-revalidate).
  const [promosByStore, setPromosByStore] = useState<PromoMap>(new Map());
  const [promosLoading, setPromosLoading] = useState(false);

  // Stable key for the unique set of stores in the current result.
  const storeSetKey = useMemo(() => {
    if (!result?.items.length) return '';
    const pairs = new Set<string>();
    for (const item of result.items) {
      for (const q of item.quotes) {
        pairs.add(`${q.chain_id}/${q.store_id}`);
      }
    }
    return Array.from(pairs).sort().join('|');
  }, [result?.items]);

  useEffect(() => {
    // No results — clear promos and bail.
    if (!storeSetKey || !result?.items.length) {
      setPromosByStore(new Map());
      setPromosLoading(false);
      return;
    }

    // Results are already rendered by the time this effect runs.
    // Start the bulk promo fetch in the background.
    setPromosLoading(true);

    const seen = new Set<string>();
    const stores: { chain_id: string; store_id: string }[] = [];
    for (const item of result.items) {
      for (const q of item.quotes) {
        const key = `${q.chain_id}/${q.store_id}`;
        if (!seen.has(key)) {
          seen.add(key);
          stores.push({ chain_id: q.chain_id, store_id: q.store_id });
        }
      }
    }

    getPromosBulk(stores).then(record => {
      setPromosByStore(new Map(Object.entries(record)));
      setPromosLoading(false);
    });
  }, [storeSetKey]); // eslint-disable-line react-hooks/exhaustive-deps

  if (isError) return <ErrorState onRetry={onRetry} />;

  if (isLoading && !result) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
          <ProductCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  const hasQuery = query.trim().length >= 2;
  if (!hasQuery || !result || result.items.length === 0) {
    return <EmptyState query={hasQuery ? query : undefined} />;
  }

  return (
    <div className={isFetching && !isLoadingMore ? 'opacity-70 transition-opacity' : ''}>
      <div className="flex items-center gap-2 mb-3">
        <p className="text-xs text-gray-400">
          {t('search.results_count', { count: result.total_matches })}
          {result.comparable_count > 0 && ` · ${t('search.comparable_count', { count: result.comparable_count })}`}
        </p>
        {promosLoading && (
          <span className="flex items-center gap-1 text-xs text-gray-300">
            <Loader2 size={10} className="animate-spin" />
            טוען מבצעים…
          </span>
        )}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {result.items
          .filter((item, i, arr) => arr.findIndex(x => x.product.item_code === item.product.item_code) === i)
          .map(item => (
            <ProductCard key={item.product.item_code} item={item} promosByStore={promosByStore} />
          ))}
      </div>

      {/* Load more */}
      {result.has_more && onLoadMore && (
        <div className="flex justify-center mt-6">
          <button
            onClick={onLoadMore}
            disabled={isLoadingMore}
            className="flex items-center gap-2 px-6 py-2.5 bg-white border border-gray-300
                       text-gray-700 rounded-lg text-sm font-medium hover:border-emerald-500
                       hover:text-emerald-600 transition-colors disabled:opacity-50"
          >
            {isLoadingMore ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                {t('load_more.loading')}
              </>
            ) : (
              t('load_more.button')
            )}
          </button>
        </div>
      )}
    </div>
  );
}
