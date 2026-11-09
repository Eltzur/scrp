import { useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { isAxiosError } from 'axios';
import { Loader2 } from 'lucide-react';
import type { SearchResult } from '../../api/client';
import EmptyState from '../EmptyState';
import ErrorState from '../ErrorState';
import { K } from './strings';
import ResultsListView from './ResultsListView';
import CompareTable from './CompareTable';
import { pageRequest, type PageSize } from '../../utils/resultViews';

export type FetchPage = (limit: number, offset: number, signal?: AbortSignal) => Promise<SearchResult>;

interface Props {
  view: 'list' | 'table';
  size: PageSize;
  clamped: boolean;
  /** Identity of the search (query + filters); part of the cache key. */
  pagedKey: unknown[];
  fetchPage: FetchPage;
  /** The endpoint's own per-request cap (/search 100, category items 60). */
  maxLimit: number;
  query: string;
  /** The selected city (null = nationwide) for the table's note. */
  city: string | null;
}

/**
 * SU11A-72: one page of results in the list or the comparison table. ONE
 * request per page (limit = page size, capped by the endpoint); the payload's
 * per-chain quotes feed both views, so opening a row or the table makes no
 * further request. The page resets when the parent re-keys this component
 * (a new search, filters or page size).
 */
export default function PagedResults({ view, size, clamped, pagedKey, fetchPage, maxLimit, query, city }: Props) {
  const { t } = useTranslation();
  const [page, setPage] = useState(0);
  const { limit, offset } = pageRequest(size, page, maxLimit);
  const q = useQuery({
    queryKey: ['paged', ...pagedKey, limit, offset],
    queryFn: ({ signal }) => fetchPage(limit, offset, signal),
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
    retry: (n, err) => !(isAxiosError(err) && err.response?.status && err.response.status < 500) && n < 1,
  });

  const items = useMemo(() => {
    const seen = new Set<string>();
    return (q.data?.items ?? []).filter(it => !seen.has(it.product.item_code) && !!seen.add(it.product.item_code));
  }, [q.data]);

  if (q.isError && !q.data) {
    const status = isAxiosError(q.error) ? q.error.response?.status ?? 0 : 0;
    return <ErrorState onRetry={() => q.refetch()} busy={[429, 503].includes(status)} />;
  }
  if (q.isLoading && !q.data) {
    return (
      <p role="status" className="flex items-center justify-center gap-2 py-16 text-sm text-gray-700">
        <Loader2 size={16} className="animate-spin" aria-hidden="true" /> {t(`${K}.loading`)}
      </p>
    );
  }
  if (!q.data || items.length === 0) return <EmptyState query={query} />;

  const data = q.data;
  const from = offset + 1;
  const to = offset + data.items.length;
  const capped = size === 0 && data.has_more;
  const go = (p: number) => { setPage(p); window.scrollTo({ top: 0, behavior: 'smooth' }); };

  return (
    <div className={q.isFetching ? 'opacity-70 transition-opacity' : ''} aria-busy={q.isFetching}>
      <p className="text-xs text-gray-700 mb-2" role="status">
        {t('search.results_count', { count: data.total_matches })} · {t(`${K}.showing`, { from, to })}
        {q.isFetching && <Loader2 size={10} className="inline animate-spin ms-2" aria-hidden="true" />}
      </p>
      {clamped && <p className="text-xs text-gray-700 mb-2">{t(`${K}.table_clamped`)}</p>}
      {capped && <p className="text-xs text-gray-700 mb-2">{t(`${K}.all_capped`, { shown: data.items.length, total: data.total_matches })}</p>}

      {view === 'list'
        ? <ResultsListView items={items} />
        : <CompareTable items={items} city={city} />}

      {size !== 0 && (page > 0 || data.has_more) && (
        <nav aria-label={t(`${K}.pager_label`)} className="flex items-center justify-center gap-3 mt-6">
          <button
            type="button"
            disabled={page === 0 || q.isFetching}
            onClick={() => go(page - 1)}
            className="min-h-[40px] px-4 rounded-lg border border-gray-500 bg-white text-sm font-medium text-gray-800
                       hover:border-emerald-700 disabled:opacity-50
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
          >
            {t(`${K}.prev`)}
          </button>
          <span className="text-sm text-gray-700" dir="ltr">{page + 1}</span>
          <button
            type="button"
            disabled={!data.has_more || q.isFetching}
            onClick={() => go(page + 1)}
            className="min-h-[40px] px-4 rounded-lg border border-gray-500 bg-white text-sm font-medium text-gray-800
                       hover:border-emerald-700 disabled:opacity-50
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
          >
            {t(`${K}.next`)}
          </button>
        </nav>
      )}
    </div>
  );
}
