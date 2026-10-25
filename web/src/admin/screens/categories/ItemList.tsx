import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { MoveRight, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import CategoryPicker from '../../../components/category/CategoryPicker';
import { pathOf } from '../../../components/category/tree';
import { bulkCat, type CatItemRow } from '../../api';
import { Button, ConfirmDialog, ErrorBox, Loading } from '../../ui';
import LabelChips from './LabelChips';
import { K, useTree, writeError } from './shared';

/**
 * A list of items (search results or a queue page) with multi-select and the
 * bulk move (SU11A-57): pick up to 100, choose a target in the picker, confirm
 * with the count and the target's path. Each row opens the item panel.
 */
const BULK_MAX = 100;

function BulkBar({ selected, onDone, onClear }: { selected: string[]; onDone: () => void; onClear: () => void }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const tree = useTree();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const m = useMutation({
    mutationFn: () => bulkCat(selected, target as string),
    onSuccess: (res) => {
      toast.success(t(`${K}.bulk.done`, { n: res.updated }));
      void qc.invalidateQueries({ queryKey: ['admin'] });
      setOpen(false);
      setTarget(null);
      onDone();
    },
    onError: (err) => toast.error(writeError(t, err)),
    onSettled: () => setAsking(false),
  });
  const path = target ? pathOf(tree.data?.nodes ?? [], target, i18n.language) : '';

  return (
    <div className="sticky bottom-0 z-10 mt-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-3 shadow-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-semibold text-emerald-900" aria-live="polite">
          {t(`${K}.bulk.selected`, { n: selected.length })}
        </span>
        <Button tone="primary" onClick={() => setOpen(v => !v)} aria-expanded={open}>
          <MoveRight size={16} aria-hidden="true" /> {t(`${K}.bulk.move`)}
        </Button>
        <Button onClick={onClear}><X size={16} aria-hidden="true" /> {t(`${K}.bulk.clear`)}</Button>
      </div>
      {open && (
        <div className="mt-3 rounded-xl bg-white p-3 border border-gray-200">
          {tree.isPending ? <Loading /> : tree.isError ? <ErrorBox error={tree.error} /> : (
            <CategoryPicker nodes={tree.data.nodes} value={target} onChange={setTarget}
              label={t(`${K}.bulk.target`)} maxHeightClass="max-h-56" />
          )}
          <Button tone="primary" className="mt-3" disabled={!target || m.isPending} onClick={() => setAsking(true)}>
            {t(`${K}.bulk.go`)}
          </Button>
        </div>
      )}
      <ConfirmDialog
        open={asking}
        message={t(`${K}.bulk.confirm`, { n: selected.length, path })}
        busy={m.isPending}
        onCancel={() => setAsking(false)}
        onConfirm={() => m.mutate()}
      />
    </div>
  );
}

export default function ItemList({ items, onOpen, showOther = false }: {
  items: CatItemRow[]; onOpen: (code: string) => void; showOther?: boolean;
}) {
  const { t } = useTranslation();
  const [sel, setSel] = useState<string[]>([]);
  const toggle = (code: string) => setSel(s => {
    if (s.includes(code)) return s.filter(c => c !== code);
    if (s.length >= BULK_MAX) { toast.error(t(`${K}.bulk.max`)); return s; }
    return [...s, code];
  });
  const pageCodes = items.map(i => i.item_code);
  const allOn = pageCodes.length > 0 && pageCodes.every(c => sel.includes(c));
  const toggleAll = () => setSel(s => allOn ? s.filter(c => !pageCodes.includes(c))
    : [...s, ...pageCodes.filter(c => !s.includes(c))].slice(0, BULK_MAX));

  return (
    <div>
      {items.length > 1 && (
        <label className="inline-flex items-center gap-2 min-h-[44px] text-sm text-gray-800 cursor-pointer">
          <input type="checkbox" checked={allOn} onChange={toggleAll} className="h-5 w-5 rounded border-gray-400" />
          {t(`${K}.bulk.select_all`)}
        </label>
      )}
      <ul className="space-y-2">
        {items.map(i => {
          const name = i.item_name || i.item_code;
          return (
            <li key={i.item_code} className="flex items-stretch gap-2 rounded-xl border border-gray-200 bg-white">
              <label className="flex items-center justify-center min-w-[44px] min-h-[44px] cursor-pointer">
                <input type="checkbox" checked={sel.includes(i.item_code)} onChange={() => toggle(i.item_code)}
                  aria-label={t(`${K}.bulk.select`, { name })} className="h-5 w-5 rounded border-gray-400" />
              </label>
              <button
                type="button"
                onClick={() => onOpen(i.item_code)}
                className="flex-1 min-w-0 text-right min-h-[48px] py-2 pe-3 rounded-xl hover:bg-gray-50
                  focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700"
              >
                <span className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-gray-900 truncate" dir="auto">{name}</span>
                  <span className="shrink-0 text-xs text-gray-500 tabular-nums">{t(`${K}.chains`, { n: i.chains_live ?? 0 })}</span>
                </span>
                <span className="block text-xs text-gray-500 font-mono" dir="ltr">{i.item_code}</span>
                <span className="mt-1 flex flex-wrap items-center gap-2 text-sm text-gray-800">
                  <span dir="auto">{i.label?.path_he ?? ''}</span>
                  <LabelChips label={i.label} />
                </span>
                {showOther && i.other && (
                  <span className="block mt-1 text-xs text-gray-700" dir="auto">
                    {t(`${K}.other_side`, { source: t(`${K}.source.${i.other.source}`), path: i.other.path_he || i.other.category_id })}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
      {sel.length > 0 && <BulkBar selected={sel} onDone={() => setSel([])} onClear={() => setSel([])} />}
    </div>
  );
}
