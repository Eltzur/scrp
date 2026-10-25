import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowRight, Check, Save, Undo2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import CategoryPicker from '../../../components/category/CategoryPicker';
import { pathOf } from '../../../components/category/tree';
import { confirmCatItem, errorCode, getCatItem, revertCat, setCatItem } from '../../api';
import { actionLabel, fmtDate } from '../../format';
import { Button, Card, ConfirmDialog, ErrorBox, Loading } from '../../ui';
import LabelChips from './LabelChips';
import { K, useTree, writeError } from './shared';

/**
 * One item (SU11A-57): its label with source / confidence / chains, a searchable
 * picker, save (manual row), "נכון" (reviewed, no change) and undo of any audited
 * change. Every action asks first and answers with a toast.
 */
type Pending = { kind: 'save' } | { kind: 'confirm' } | { kind: 'revert'; auditId: number };

export default function ItemPanel({ code, onBack }: { code: string; onBack: () => void }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const tree = useTree();
  const [picked, setPicked] = useState<string | null>(null);
  const [pending, setPending] = useState<Pending | null>(null);
  const q = useQuery({ queryKey: ['admin', 'cat-item', code], queryFn: () => getCatItem(code), retry: 0 });

  const m = useMutation({
    mutationFn: async (p: Pending) => {
      if (p.kind === 'save') return setCatItem(code, picked as string);
      if (p.kind === 'confirm') return confirmCatItem(code);
      return revertCat(p.auditId);
    },
    onSuccess: (_res, p) => {
      toast.success(t(`${K}.item.done_${p.kind}`));
      setPicked(null);
      void qc.invalidateQueries({ queryKey: ['admin'] });
    },
    onError: (err) => toast.error(writeError(t, err)),
    onSettled: () => setPending(null),
  });

  const back = (
    <Button onClick={onBack} className="mb-3">
      <ArrowRight size={16} aria-hidden="true" /> {t('admin.common.back')}
    </Button>
  );
  if (q.isPending) return <div>{back}<Loading /></div>;
  if (q.isError) {
    return <div>{back}{errorCode(q.error) === 'item_not_found'
      ? <p className="text-sm text-gray-700">{t(`${K}.item.not_found`)}</p>
      : <ErrorBox error={q.error} onRetry={() => void q.refetch()} />}</div>;
  }
  const d = q.data;
  const lab = d.label;
  const nodes = tree.data?.nodes ?? [];
  const pickedPath = picked ? pathOf(nodes, picked, i18n.language) : '';
  const message = !pending ? ''
    : pending.kind === 'save' ? t(`${K}.item.confirm_save`, { path: pickedPath })
      : pending.kind === 'confirm' ? t(`${K}.item.confirm_confirm`) : t(`${K}.item.confirm_revert`);

  return (
    <div>
      {back}
      <Card title={d.item_name || d.item_code} aside={<LabelChips label={lab} />}>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
          <dt className="text-gray-500">{t(`${K}.item.barcode`)}</dt>
          <dd dir="ltr" className="text-right font-mono">{d.item_code}</dd>
          <dt className="text-gray-500">{t(`${K}.item.current`)}</dt>
          <dd className="font-semibold text-gray-900">{lab ? lab.path_he : t(`${K}.unlabeled`)}</dd>
          {lab && (
            <>
              <dt className="text-gray-500">{t(`${K}.item.decided_at`)}</dt>
              <dd>{fmtDate(lab.decided_at)}</dd>
              {lab.detail && (
                <>
                  <dt className="text-gray-500">{t(`${K}.item.detail`)}</dt>
                  <dd className="break-words text-gray-800" dir="auto">{lab.detail}</dd>
                </>
              )}
              {lab.model && (
                <>
                  <dt className="text-gray-500">{t(`${K}.item.model`)}</dt>
                  <dd dir="ltr" className="text-right font-mono text-xs">{lab.model}</dd>
                </>
              )}
            </>
          )}
          <dt className="text-gray-500">{t(`${K}.item.chains_live`)}</dt>
          <dd className="tabular-nums">{d.chains_live ?? '—'}</dd>
        </dl>
        {d.open_suggestions > 0 && (
          <p className="mt-2 text-sm text-amber-900">{t(`${K}.item.open_suggestions`, { n: d.open_suggestions })}</p>
        )}

        <div className="mt-4">
          {tree.isPending ? <Loading /> : tree.isError ? <ErrorBox error={tree.error} onRetry={() => void tree.refetch()} /> : (
            <CategoryPicker
              nodes={nodes}
              value={picked}
              onChange={setPicked}
              currentId={lab?.category_id}
              label={t(`${K}.item.new_category`)}
            />
          )}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button tone="primary" disabled={!picked || m.isPending} onClick={() => setPending({ kind: 'save' })}>
            <Save size={16} aria-hidden="true" /> {t(`${K}.item.save`)}
          </Button>
          <Button disabled={!lab || lab.reviewed || m.isPending} onClick={() => setPending({ kind: 'confirm' })}
            title={t(`${K}.item.confirm_hint`)}>
            <Check size={16} aria-hidden="true" /> {t(`${K}.item.confirm`)}
          </Button>
        </div>
        {pickedPath && <p className="mt-2 text-sm text-gray-700" aria-live="polite">→ {pickedPath}</p>}

        <h3 className="text-sm font-semibold text-gray-900 mt-5 mb-2">{t(`${K}.item.audit`)}</h3>
        {d.audit.length === 0 ? <p className="text-sm text-gray-500">{t(`${K}.item.audit_empty`)}</p> : (
          <ul className="space-y-2">
            {d.audit.map(a => (
              <li key={a.id} className="rounded-lg border border-gray-200 p-2 text-sm flex flex-wrap items-center justify-between gap-2">
                <span>
                  <span className="font-medium">{actionLabel(t, a.action)}</span>
                  <span className="text-gray-500 text-xs"> · {fmtDate(a.at)}</span>
                  {(a.old_category_id || a.new_category_id) && (
                    <span className="block text-xs text-gray-700" dir="ltr">
                      {(a.old_category_id ?? '—')} → {(a.new_category_id ?? '—')}
                    </span>
                  )}
                </span>
                {a.revertible && (
                  <Button onClick={() => setPending({ kind: 'revert', auditId: a.id })} disabled={m.isPending}>
                    <Undo2 size={16} aria-hidden="true" /> {t(`${K}.item.revert`)}
                  </Button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <ConfirmDialog
        open={pending !== null}
        message={message}
        busy={m.isPending}
        onCancel={() => setPending(null)}
        onConfirm={() => pending && m.mutate(pending)}
      />
    </div>
  );
}
