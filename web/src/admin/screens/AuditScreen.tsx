import { useInfiniteQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getAudit } from '../api';
import { Button, ErrorBox, Loading } from '../ui';
import { actionLabel, fmtDate } from '../format';

/** יומן פעולות (SU11A-54). The admin is shown as a short hash, never by name. */

/** SU11A-57: category changes carry old / new label objects: show their id. */
function detailValue(v: unknown): string {
  if (v === null) return '—';
  if (typeof v === 'object') {
    const id = (v as { category_id?: unknown }).category_id;
    return typeof id === 'string' ? id : JSON.stringify(v);
  }
  return String(v);
}

export default function AuditScreen() {
  const { t } = useTranslation();
  const q = useInfiniteQuery({
    queryKey: ['admin', 'audit'],
    queryFn: ({ pageParam }) => getAudit(pageParam),
    initialPageParam: null as number | null,
    getNextPageParam: (last) => last.next_before,
    retry: 0,
  });

  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} onRetry={() => void q.refetch()} />;
  const items = q.data.pages.flatMap(p => p.items);
  if (items.length === 0) return <p className="text-sm text-gray-700 py-6">{t('admin.audit.empty')}</p>;

  return (
    <div>
      <ul className="space-y-2">
        {items.map(i => (
          <li key={i.id} className="rounded-xl border border-gray-200 bg-white p-3 text-sm">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-gray-900">{actionLabel(t, i.action)}</span>
              <span className="text-xs text-gray-500">{fmtDate(i.at)}</span>
            </div>
            <dl className="mt-1 text-xs text-gray-700 grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
              <dt className="text-gray-500">{t('admin.audit.target')}</dt>
              <dd dir="ltr" className="text-right">{i.target_type} #{i.target_id}</dd>
              <dt className="text-gray-500">{t('admin.audit.actor')}</dt>
              <dd dir="ltr" className="text-right font-mono">{i.actor}</dd>
              {i.detail && (
                <>
                  <dt className="text-gray-500">{t('admin.audit.detail')}</dt>
                  <dd dir="ltr" className="text-right font-mono break-all">
                    {Object.entries(i.detail).map(([k, v]) => `${k}=${detailValue(v)}`).join('  ')}
                  </dd>
                </>
              )}
            </dl>
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
