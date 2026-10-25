import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { getStatus, type BuildStamp } from '../api';
import { Button, Card, ErrorBox, Loading } from '../ui';
import { fmtBytes, fmtDate, freshness } from '../format';

/** לוח בקרה: chain freshness, search build stamps, counters, server (SU11A-54). */
const DOT = {
  today: 'bg-emerald-600',
  yesterday: 'bg-amber-500',
  older: 'bg-rose-600',
  never: 'bg-rose-600',
} as const;

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  const { t } = useTranslation();
  return (
    <div className="flex justify-between gap-3 py-1.5 border-b border-gray-100 last:border-0 text-sm">
      <dt className="text-gray-600">{label}</dt>
      <dd className="font-medium text-gray-900 tabular-nums" dir="ltr">
        {value == null ? <span className="text-gray-500">{t('admin.common.unavailable')}</span> : value}
      </dd>
    </div>
  );
}

function Build({ label, b }: { label: string; b: BuildStamp | null }) {
  const { t } = useTranslation();
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-800 mt-2">{label}</h3>
      <dl>
        <Row label={t('admin.status.built_at')} value={b?.built_at ? fmtDate(b.built_at) : null} />
        <Row label={t('admin.status.rows')} value={b?.rows_approx?.toLocaleString('he-IL') ?? null} />
      </dl>
    </div>
  );
}

export default function StatusScreen() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ['admin', 'status'], queryFn: getStatus, refetchInterval: 60_000, retry: 0 });

  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} onRetry={() => void q.refetch()} />;
  const s = q.data;
  const now = new Date();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-gray-600">{t('admin.status.updated', { time: fmtDate(s.generated_at) })}</p>
        <Button onClick={() => void q.refetch()} disabled={q.isFetching} aria-label={t('admin.common.refresh')}>
          <RefreshCw size={16} className={q.isFetching ? 'animate-spin' : ''} aria-hidden="true" />
          {t('admin.common.refresh')}
        </Button>
      </div>

      <Card title={t('admin.status.chains')}>
        {s.chains == null ? <p className="text-sm text-gray-500">{t('admin.common.unavailable')}</p> : (
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-right text-gray-600 border-b border-gray-200">
                  <th scope="col" className="py-2 px-1 font-medium">{t('admin.status.chain')}</th>
                  <th scope="col" className="py-2 px-1 font-medium">{t('admin.status.last_update')}</th>
                  <th scope="col" className="py-2 px-1 font-medium">{t('admin.status.stores')}</th>
                </tr>
              </thead>
              <tbody>
                {s.chains.map(c => {
                  const f = freshness(c.last_loaded_at, now);
                  return (
                    <tr key={c.chain_name} className="border-b border-gray-100 last:border-0">
                      <th scope="row" className="py-2 px-1 text-right font-medium text-gray-900">{c.chain_name}</th>
                      <td className="py-2 px-1">
                        <span className="inline-flex items-center gap-2">
                          <span className={`inline-block w-2.5 h-2.5 rounded-full ${DOT[f]}`} aria-hidden="true" />
                          <span>{t(`admin.status.fresh_${f === 'never' ? 'older' : f}`)}</span>
                          <span className="text-gray-500 text-xs" dir="ltr">
                            {c.last_loaded_at ? fmtDate(c.last_loaded_at) : t('admin.status.never')}
                          </span>
                        </span>
                      </td>
                      <td className="py-2 px-1 tabular-nums" dir="ltr">
                        {c.stores_loaded_72h == null ? '—' : `${c.stores_loaded_72h} / ${c.stores_configured ?? '—'}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title={t('admin.status.search')}>
          <Build label={t('admin.status.search_items')} b={s.search_items} />
          <Build label={t('admin.status.search_prices')} b={s.search_item_prices} />
        </Card>

        <Card title={t('admin.status.moderation')}>
          <dl>
            <Row label={t('admin.status.pending')} value={s.moderation?.pending} />
            <Row label={t('admin.status.hidden_7d')} value={s.moderation?.hidden_7d} />
            <Row label={t('admin.status.banned_users')} value={s.moderation?.banned_users} />
          </dl>
        </Card>

        {/* SU11A-57: null until su11a57_category_suggestions.sql is applied. */}
        <Card title={t('admin.status.categories')}>
          <dl>
            <Row label={t('admin.status.pending_suggestions')} value={s.category_suggestions?.pending} />
            <Row label={t('admin.status.pending_items')} value={s.category_suggestions?.pending_items} />
          </dl>
        </Card>

        <Card title={t('admin.status.counters')}>
          <dl>
            <Row label={t('admin.status.requests')} value={s.counters.requests.toLocaleString('he-IL')} />
            <Row label={t('admin.status.http_5xx')} value={s.counters.http_5xx} />
            <Row label={t('admin.status.query_timeout')} value={s.counters.query_timeout} />
            <Row label={t('admin.status.http_429')} value={s.counters.http_429} />
          </dl>
          <p className="text-xs text-gray-500 mt-2">
            {t('admin.status.counters_note', { pid: s.counters.pid, since: fmtDate(s.counters.since) })}
          </p>
        </Card>

        <Card title={t('admin.status.system')}>
          <dl>
            <Row label={t('admin.status.db_size')} value={fmtBytes(s.db_size_bytes)} />
            <Row label={t('admin.status.disk_free')}
              value={s.disk ? `${fmtBytes(s.disk.free_bytes)} / ${fmtBytes(s.disk.total_bytes)}` : null} />
            <Row label={t('admin.status.process_rss')} value={fmtBytes(s.memory.process_rss_bytes)} />
            <Row label={t('admin.status.system_memory')}
              value={s.memory.system_available_bytes == null ? null
                : `${fmtBytes(s.memory.system_available_bytes)} / ${fmtBytes(s.memory.system_total_bytes)}`} />
          </dl>
        </Card>
      </div>
    </div>
  );
}
