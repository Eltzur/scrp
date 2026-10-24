import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { banAuthor, errorCode, getQueue, getRating, moderate, type QueueItem } from '../api';
import { Button, Card, ConfirmDialog, ErrorBox, Loading, RatingStatus } from '../ui';
import { fmtDate } from '../format';

/**
 * ביקורות לטיפול (SU11A-54): the queue (auto-refresh every 60 s) and one
 * rating's detail with hide / keep / restore / ban. Every action asks first and
 * reports the result in a toast. No author or reporter identity is shown: the
 * API never sends it.
 */
type Action = 'hide' | 'keep' | 'restore' | 'ban' | 'unban';

function sourceLabel(t: (k: string, o?: Record<string, unknown>) => string, s: string) {
  return t(`admin.queue.source_${s}`, { defaultValue: s });
}

function QueueRow({ item, onOpen }: { item: QueueItem; onOpen: () => void }) {
  const { t } = useTranslation();
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="w-full text-right min-h-[48px] p-3 rounded-xl border border-gray-200 bg-white hover:bg-gray-50
          focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700"
      >
        <span className="flex items-center justify-between gap-2">
          <span className="font-semibold text-gray-900 truncate">{item.item_name || item.item_code}</span>
          <RatingStatus status={item.status} />
        </span>
        <span className="text-sm text-gray-700 mt-1 line-clamp-2">
          {item.comment || t('admin.rating.no_comment')}
        </span>
        <span className="block text-xs text-gray-500 mt-1">
          {t('admin.queue.reports', { n: item.report_count })}
          {item.report_sources.length > 0 && ` · ${item.report_sources.map(s => sourceLabel(t, s)).join(', ')}`}
          {' · '}{fmtDate(item.latest_report_at || item.created_at)}
        </span>
      </button>
    </li>
  );
}

function Detail({ id, onBack }: { id: number; onBack: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [pending, setPending] = useState<Action | null>(null);
  const q = useQuery({ queryKey: ['admin', 'rating', id], queryFn: () => getRating(id), retry: 0 });

  const m = useMutation({
    mutationFn: async (a: Action) => {
      if (a === 'ban' || a === 'unban') return banAuthor(id, a === 'ban');
      return moderate(id, a);
    },
    onSuccess: (res, a) => {
      const hidden = 'ratings_hidden' in res ? res.ratings_hidden : 0;
      toast.success(t(`admin.queue.done_${a}`, { n: hidden }));
      void qc.invalidateQueries({ queryKey: ['admin'] });
    },
    onError: (err) => {
      toast.error(errorCode(err) === 'http_404' ? t('admin.queue.not_found')
        : errorCode(err) === 'network' ? t('admin.common.network') : t('admin.common.error'));
    },
    onSettled: () => setPending(null),
  });

  const back = (
    <Button onClick={onBack} className="mb-3">
      <ArrowRight size={16} aria-hidden="true" /> {t('admin.common.back')}
    </Button>
  );
  if (q.isPending) return <div>{back}<Loading /></div>;
  if (q.isError) {
    return <div>{back}{errorCode(q.error) === 'http_404'
      ? <p className="text-sm text-gray-700">{t('admin.queue.not_found')}</p>
      : <ErrorBox error={q.error} onRetry={() => void q.refetch()} />}</div>;
  }
  const r = q.data;
  const banned = r.author.banned === true;
  const actions: { a: Action; tone: 'primary' | 'neutral' | 'danger'; show: boolean }[] = [
    { a: 'hide', tone: 'danger', show: r.status !== 'hidden' },
    { a: 'keep', tone: 'neutral', show: true },
    { a: 'restore', tone: 'primary', show: r.status !== 'active' },
    { a: banned ? 'unban' : 'ban', tone: banned ? 'neutral' : 'danger', show: r.author.banned != null },
  ];

  return (
    <div>
      {back}
      <Card title={r.item_name || r.item_code} aside={<RatingStatus status={r.status} />}>
        <p className="text-xs text-gray-500 mb-2" dir="ltr">{r.item_code} · #{r.id}</p>
        <p className="text-sm text-gray-800 mb-1">{t('admin.rating.score', { n: r.rating })}</p>
        <blockquote className="whitespace-pre-wrap break-words rounded-xl bg-gray-50 border border-gray-200 p-3 text-base text-gray-900">
          {r.comment || t('admin.rating.no_comment')}
        </blockquote>
        <p className="text-xs text-gray-500 mt-2">
          {t('admin.rating.created')}: {fmtDate(r.created_at)}
          {r.reviewed_at && <> · {t('admin.rating.reviewed')}: {fmtDate(r.reviewed_at)}</>}
        </p>
        <p className="text-sm text-gray-700 mt-3">
          {t('admin.queue.author')}: {banned ? t('admin.queue.author_banned') : t('admin.queue.author_not_banned')}
          {r.author.active_ratings != null && <> · {t('admin.queue.author_active', { n: r.author.active_ratings })}</>}
        </p>

        <h3 className="text-sm font-semibold text-gray-900 mt-4 mb-2">{t('admin.queue.reports', { n: r.reports.length })}</h3>
        {r.reports.length === 0 ? <p className="text-sm text-gray-500">{t('admin.queue.no_reports')}</p> : (
          <ul className="space-y-2">
            {r.reports.map(p => (
              <li key={p.id} className="text-sm rounded-lg border border-gray-200 p-2">
                <span className="font-medium">{sourceLabel(t, p.source)}</span>
                <span className="text-gray-500 text-xs"> · {fmtDate(p.created_at)}</span>
                {p.reason && <p className="text-gray-800 mt-1 break-words">{p.reason}</p>}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-5 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
          {actions.filter(x => x.show).map(x => (
            <Button key={x.a} tone={x.tone} onClick={() => setPending(x.a)} disabled={m.isPending}>
              {t(`admin.queue.${x.a}`)}
            </Button>
          ))}
        </div>
      </Card>

      <ConfirmDialog
        open={pending !== null}
        message={pending ? t(`admin.queue.confirm_${pending}`, { n: r.author.active_ratings ?? 0 }) : ''}
        tone={pending === 'hide' || pending === 'ban' ? 'danger' : 'primary'}
        busy={m.isPending}
        onCancel={() => setPending(null)}
        onConfirm={() => pending && m.mutate(pending)}
      />
    </div>
  );
}

export default function QueueScreen() {
  const { t } = useTranslation();
  const [open, setOpen] = useState<number | null>(null);
  const q = useQuery({ queryKey: ['admin', 'queue'], queryFn: getQueue, refetchInterval: 60_000, retry: 0 });

  if (open !== null) return <Detail id={open} onBack={() => setOpen(null)} />;
  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} onRetry={() => void q.refetch()} />;
  return (
    <div>
      <p className="text-xs text-gray-500 mb-3">{t('admin.queue.auto_refresh')}</p>
      {q.data.items.length === 0
        ? <p className="text-sm text-gray-700 py-6">{t('admin.queue.empty')}</p>
        : <ul className="space-y-2">{q.data.items.map(i => <QueueRow key={i.id} item={i} onOpen={() => setOpen(i.id)} />)}</ul>}
    </div>
  );
}
