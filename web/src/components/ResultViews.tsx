import { lazy, Suspense, useState, type ComponentProps } from 'react';
import { Loader2 } from 'lucide-react';
import ResultsList from './ResultsList';
import type { FetchPage } from './results/PagedResults';
import {
  effectivePageSize, loadPageSize, loadView, savePageSize, saveView,
  type PageSize, type ViewMode,
} from '../utils/resultViewPrefs';

// SU11A-72: the switcher and the list / table views are lazy chunks; the grid
// (today's cards, unchanged) renders without waiting for them.
const ViewSwitcher = lazy(() => import('./results/ViewSwitcher'));
const PagedResults = lazy(() => import('./results/PagedResults'));

type Props = ComponentProps<typeof ResultsList> & {
  /** A search is on screen (the switcher shows only then). */
  active: boolean;
  /** Identity of the search (query + filters): a change restarts the list / table at page 1. */
  pagedKey: unknown[];
  /** One page for the list / table; undefined = not available (group_by=store rows). */
  fetchPage?: FetchPage;
  /** The endpoint's per-request cap: /search and /compare 100, category items 60. */
  maxLimit: number;
  /** The selected city for the table's note (null = nationwide). */
  city: string | null;
};

/**
 * SU11A-72: grid / list / comparison table for search and category results.
 * The choice and the page size are remembered per browser (localStorage), never
 * in the URL, so switching is not a page view.
 */
export default function ResultViews({ active, pagedKey, fetchPage, maxLimit, city, ...grid }: Props) {
  const [view, setView] = useState<ViewMode>(() => loadView());
  const [size, setSize] = useState<PageSize>(() => loadPageSize());
  const paged = !!fetchPage;
  const shown: ViewMode = active && paged ? view : 'grid';
  const eff = effectivePageSize(shown, size);

  return (
    <>
      {active && (
        <Suspense fallback={<div className="min-h-[42px] mb-3" />}>
          <ViewSwitcher
            view={paged ? view : 'grid'}
            wanted={view}
            size={size}
            onView={v => { setView(v); saveView(v); }}
            onSize={n => { setSize(n); savePageSize(n); }}
            pagedAvailable={paged}
          />
        </Suspense>
      )}
      {shown === 'grid' || !fetchPage ? (
        <ResultsList {...grid} />
      ) : (
        <Suspense fallback={<p className="flex justify-center py-16"><Loader2 size={18} className="animate-spin text-gray-600" aria-hidden="true" /></p>}>
          <PagedResults
            key={JSON.stringify([pagedKey, shown, eff.size])}
            view={shown}
            size={eff.size}
            clamped={eff.clamped}
            pagedKey={pagedKey}
            fetchPage={fetchPage}
            maxLimit={maxLimit}
            query={grid.query}
            city={city}
          />
        </Suspense>
      )}
    </>
  );
}
