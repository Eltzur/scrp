import type { SearchResult } from '../api/client';
import ProductCard from './ProductCard';
import ProductCardSkeleton from './ProductCardSkeleton';
import EmptyState from './EmptyState';
import ErrorState from './ErrorState';

interface Props {
  result: SearchResult | undefined;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  query: string;
  onRetry: () => void;
}

const SKELETON_COUNT = 6;

export default function ResultsList({ result, isLoading, isFetching, isError, query, onRetry }: Props) {
  if (isError) return <ErrorState onRetry={onRetry} />;

  // First load — no previous data yet → show skeletons
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
    <div className={isFetching ? 'opacity-70 transition-opacity' : ''}>
      <p className="text-xs text-gray-400 mb-3">
        {result.total_matches} products found
        {result.comparable_count > 0 && ` · ${result.comparable_count} comparable across chains`}
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {result.items.map(item => (
          <ProductCard key={item.product.item_code} item={item} />
        ))}
      </div>
    </div>
  );
}
