import { useInfiniteQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getHistory, type Cursor } from '../api';
import { Button, ErrorBox, Loading, RatingStatus } from '../ui';
import { actionLabel, fmtDate } from '../format';

/** היסטוריה (SU11A-54): recent moderator decisions, newest first. */
export default function HistoryScreen() {
  const { t } = useTranslation();
  const q = useInfiniteQuery({
    queryKey: ['admin', 'history'],
    queryFn: ({ pageParam }) => getHistory(pageParam),
    initialPageParam: null as Cursor | null,
    getNextPageParam: (last) => last.next,
    retry: 0,
  });

  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} onRetry={() => void q.refetch()} />;
  const items = q.data.pages.flatMap(p => p.items);
  if (items.length === 0) return <p className="text-sm text-gray-700 py-6">{t('admin.history.empty')}</p>;

  return (
    <div>
      <ul className="space-y-2">
        {items.map(i => (
          <li key={i.id} className="rounded-xl border border-gray-200 bg-white p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-gray-900 truncate">{i.item_name || i.item_code}</span>
              <RatingStatus status={i.status} />
            </div>
            <p className="text-sm text-gray-700 mt-1 line-clamp-2">{i.comment || t('admin.rating.no_comment')}</p>
            <p className="text-xs text-gray-500 mt-1">
              {fmtDate(i.reviewed_at)} · {t('admin.history.last_action')}:{' '}
              {i.last_action ? actionLabel(t, i.last_action) : t('admin.history.cli')}
              <span dir="ltr"> · #{i.id}</span>
            </p>
          </li>
        ))}
      </ul>
      {q.hasNextPage && (
        <Button className="mt-4 w-full sm:w-auto" onClick={() => void q.fetchNextPage()} disabled={q.isFetchingNextPage}>
          {t('admin.common.load_more')}
        </Button>
      )}
    </div>
  );
}
