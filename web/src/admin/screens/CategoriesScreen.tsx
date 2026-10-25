import { useEffect, useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { getCatQueue, searchCatItems, type CatQueueKind } from '../api';
import { Button, ErrorBox, Loading } from '../ui';
import ItemList from './categories/ItemList';
import ItemPanel from './categories/ItemPanel';
import SuggestionsQueue from './categories/SuggestionsQueue';
import { K } from './categories/shared';

/**
 * קטגוריות (SU11A-57): search by name or barcode, the item panel, and four
 * queues (low confidence, rules vs AI, unclassified live items, user
 * suggestions), each paged and sorted by chains_live. Every write is a manual
 * label recorded in the audit log; nothing here changes how automated runs
 * label other items.
 */
const VIEWS = ['search', 'low', 'disagreements', 'unclassified', 'suggestions'] as const;
type View = typeof VIEWS[number];

function useDebounced(v: string, ms = 350) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const h = setTimeout(() => setD(v), ms);
    return () => clearTimeout(h);
  }, [v, ms]);
  return d;
}

function SearchView({ onOpen }: { onOpen: (code: string) => void }) {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  const q = useDebounced(text.trim());
  const r = useQuery({ queryKey: ['admin', 'cat-search', q], queryFn: () => searchCatItems(q), enabled: q.length >= 2, retry: 0 });
  return (
    <div>
      <label htmlFor="cat-admin-q" className="block text-sm font-semibold text-gray-800 mb-1">{t(`${K}.search_label`)}</label>
      <div className="relative">
        <Search size={16} className="absolute top-1/2 -translate-y-1/2 start-3 text-gray-500 pointer-events-none" aria-hidden="true" />
        <input
          id="cat-admin-q"
          type="search"
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder={t(`${K}.search_placeholder`)}
          aria-describedby="cat-admin-q-hint"
          dir="auto"
          autoComplete="off"
          className="w-full min-h-[44px] ps-9 pe-3 rounded-xl border border-gray-300 bg-white text-base
            focus:outline-none focus:ring-2 focus:ring-emerald-600"
        />
      </div>
      <p id="cat-admin-q-hint" className="text-xs text-gray-500 mt-1">{t(`${K}.search_hint`)}</p>
      <div className="mt-3">
        {q.length < 2 ? null : r.isPending ? <Loading /> : r.isError ? <ErrorBox error={r.error} onRetry={() => void r.refetch()} />
          : r.data.items.length === 0 ? <p className="text-sm text-gray-700 py-4">{t(`${K}.no_results`)}</p>
            : <ItemList items={r.data.items} onOpen={onOpen} />}
      </div>
    </div>
  );
}

function QueueView({ kind, onOpen }: { kind: Exclude<CatQueueKind, 'suggestions'>; onOpen: (code: string) => void }) {
  const { t } = useTranslation();
  const q = useInfiniteQuery({
    queryKey: ['admin', 'cat-queue', kind],
    queryFn: ({ pageParam }) => getCatQueue(kind, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last) => last.next_offset,
    retry: 0,
  });
  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} onRetry={() => void q.refetch()} />;
  const items = q.data.pages.flatMap(p => p.items);
  if (items.length === 0) return <p className="text-sm text-gray-700 py-6">{t(`${K}.queue_empty`)}</p>;
  return (
    <div>
      <p className="text-xs text-gray-500 mb-2">
        {t(`${K}.queue_total`, { n: q.data.pages[0].total.toLocaleString('he-IL') })} · {t(`${K}.sorted`)}
      </p>
      <ItemList items={items} onOpen={onOpen} showOther={kind === 'disagreements'} />
      {q.hasNextPage && (
        <Button className="mt-4 w-full sm:w-auto" onClick={() => void q.fetchNextPage()} disabled={q.isFetchingNextPage}>
          {t('admin.common.load_more')}
        </Button>
      )}
    </div>
  );
}

export default function CategoriesScreen() {
  const { t } = useTranslation();
  const [view, setView] = useState<View>('search');
  const [open, setOpen] = useState<string | null>(null);

  if (open) return <ItemPanel code={open} onBack={() => setOpen(null)} />;
  return (
    <div>
      <div role="tablist" aria-label={t(`${K}.tabs.label`)} className="flex gap-1 overflow-x-auto mb-4 -mx-1 px-1">
        {VIEWS.map(v => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={view === v}
            onClick={() => setView(v)}
            className={`shrink-0 min-h-[44px] px-3 rounded-full text-sm font-semibold border
              focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700
              ${view === v ? 'bg-emerald-700 text-white border-emerald-700' : 'bg-white text-gray-800 border-gray-300 hover:bg-gray-50'}`}
          >
            {t(`${K}.tabs.${v}`)}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {view === 'search' && <SearchView onOpen={setOpen} />}
        {view === 'suggestions' && <SuggestionsQueue onOpen={setOpen} />}
        {view !== 'search' && view !== 'suggestions' && <QueueView key={view} kind={view} onOpen={setOpen} />}
      </div>
    </div>
  );
}
