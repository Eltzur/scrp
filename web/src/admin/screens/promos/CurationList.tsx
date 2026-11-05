import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowDown, ArrowUp, Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { getCuration, removeCuration, updateCuration, type CurationPatch, type CurationRow } from '../../api';
import { fmtDate } from '../../format';
import { Button, ConfirmDialog, ErrorBox, Loading } from '../../ui';
import PromoCard from './PromoCard';
import { K, writeError } from './shared';

/**
 * The active pins (rank order, moved with up / down), the active hides, and
 * the expired rows (past their end date, or the promotion left the data) of
 * the מבצעים tab (SU11A-58). Removing keeps the row for the record (audited).
 * SU11A-62: each pin shows the cities where it is visible, with a warning when
 * there are none or checkCity is not one of them.
 */
type View = 'pins' | 'hides' | 'expired';
type Ask = { row: CurationRow; what: 'remove' | 'sponsor' } | null;

function useWrite() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (a: { id: number; patch?: CurationPatch; remove?: boolean; ok: string }) => {
      await (a.remove ? removeCuration(a.id) : updateCuration(a.id, a.patch ?? {}));
      return a.ok;
    },
    onSuccess: (ok) => {
      toast.success(t(`${K}.toast.${ok}`));
      void qc.invalidateQueries({ queryKey: ['admin'] });
    },
    onError: (err) => toast.error(writeError(t, err)),
  });
}

function Meta({ r }: { r: CurationRow }) {
  const { t } = useTranslation();
  const bits: string[] = [];
  if (r.status === 'scheduled') bits.push(t(`${K}.list.scheduled`, { date: fmtDate(r.starts_at) }));
  if (r.status === 'expired_date' || r.status === 'expired_missing') bits.push(t(`${K}.list.${r.status}`));
  else bits.push(r.ends_at ? t(`${K}.list.until`, { date: fmtDate(r.ends_at) }) : t(`${K}.list.no_end`));
  if (r.note) bits.push(t(`${K}.list.${r.kind === 'hide' ? 'reason' : 'note'}`, { note: r.note }));
  return <p className="mt-2 text-xs text-gray-700" dir="auto">{bits.join(' · ')}</p>;
}

export default function CurationList({ view, checkCity }: { view: View; checkCity?: string }) {
  const { t } = useTranslation();
  const state = view === 'expired' ? 'expired' : 'active';
  const q = useQuery({ queryKey: ['admin', 'promo-curation', state], queryFn: () => getCuration(state), retry: 0 });
  const w = useWrite();
  const [ask, setAsk] = useState<Ask>(null);

  if (q.isPending) return <Loading />;
  if (q.isError) return <ErrorBox error={q.error} onRetry={() => void q.refetch()} />;
  const rows = q.data.items.filter(r => view === 'expired' || r.kind === (view === 'pins' ? 'pin' : 'hide'));
  if (rows.length === 0) return <p className="text-sm text-gray-700 py-6">{t(`${K}.list.empty_${view}`)}</p>;

  const move = (r: CurationRow, rank: number) => w.mutate({ id: r.id, patch: { rank }, ok: 'moved' });
  return (
    <>
      <ol className="space-y-3">
        {rows.map((r, i) => {
          const name = r.promo.promo_description || r.promo.promo_id;
          return (
            <li key={r.id}>
              <PromoCard p={r.promo} checkCity={checkCity}>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  {r.kind === 'pin' && (
                    <span className="text-xs font-semibold rounded-full border border-emerald-300 bg-emerald-50 text-emerald-900 px-2 py-0.5">
                      {t(`${K}.list.rank`, { rank: r.rank })}
                    </span>
                  )}
                  {r.kind === 'hide' && (
                    <span className="text-xs font-semibold rounded-full border border-gray-300 bg-gray-100 text-gray-800 px-2 py-0.5">
                      {t(`${K}.card.hidden`)}
                    </span>
                  )}
                  {r.sponsored && (
                    <span className="text-xs font-semibold rounded border border-gray-400 bg-white text-gray-800 px-1.5 py-0.5">
                      {t(`${K}.list.sponsored`)}
                    </span>
                  )}
                </div>
                <Meta r={r} />
                <div className="mt-3 flex flex-wrap gap-2">
                  {view === 'pins' && (
                    <>
                      <Button onClick={() => move(r, (r.rank ?? 1) - 1)} disabled={i === 0 || w.isPending}
                        aria-label={t(`${K}.list.up`, { name })}>
                        <ArrowUp size={16} aria-hidden="true" />
                      </Button>
                      <Button onClick={() => move(r, (r.rank ?? 1) + 1)} disabled={i === rows.length - 1 || w.isPending}
                        aria-label={t(`${K}.list.down`, { name })}>
                        <ArrowDown size={16} aria-hidden="true" />
                      </Button>
                      <Button disabled={w.isPending}
                        onClick={() => (r.sponsored
                          ? w.mutate({ id: r.id, patch: { sponsored: false }, ok: 'saved' })
                          : setAsk({ row: r, what: 'sponsor' }))}>
                        {t(`${K}.list.${r.sponsored ? 'unset_sponsored' : 'set_sponsored'}`)}
                      </Button>
                    </>
                  )}
                  <Button tone="danger" disabled={w.isPending} onClick={() => setAsk({ row: r, what: 'remove' })}>
                    <Trash2 size={16} aria-hidden="true" /> {t(`${K}.list.remove`)}
                  </Button>
                </div>
              </PromoCard>
            </li>
          );
        })}
      </ol>
      <ConfirmDialog
        open={ask !== null}
        message={ask?.what === 'sponsor' ? t(`${K}.list.sponsored_confirm`) : t(`${K}.list.remove_confirm`)}
        tone={ask?.what === 'remove' ? 'danger' : 'primary'}
        busy={w.isPending}
        onConfirm={() => {
          if (!ask) return;
          w.mutate(ask.what === 'remove' ? { id: ask.row.id, remove: true, ok: 'removed' }
            : { id: ask.row.id, patch: { sponsored: true }, ok: 'saved' }, { onSettled: () => setAsk(null) });
        }}
        onCancel={() => setAsk(null)}
      />
    </>
  );
}
