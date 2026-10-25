import { useState } from 'react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import CategoryPicker from '../../../components/category/CategoryPicker';
import { pathOf } from '../../../components/category/tree';
import { acceptSuggestions, getCatQueue, rejectSuggestions, type SuggestionGroup } from '../../api';
import { fmtDate } from '../../format';
import { Button, Card, ConfirmDialog, ErrorBox, Loading } from '../../ui';
import LabelChips from './LabelChips';
import { K, useTree, writeError } from './shared';

/**
 * הצעות קטגוריה (SU11A-57): open user suggestions grouped by item, busiest items
 * first (chains_live). Shows how many, which ids with counts, and the latest
 * comments (clamped). Accept with a choice (a suggested id or any other from the
 * picker) writes a manual row and closes every open suggestion of the item;
 * reject closes them without a change. Who suggested is never shown: the API
 * does not send it.
 */
const OTHER = '__other__';

function Group({ g, onOpen }: { g: SuggestionGroup; onOpen: (code: string) => void }) {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const tree = useTree();
  const [choice, setChoice] = useState<string>(g.suggested[0]?.category_id ?? OTHER);
  const [other, setOther] = useState<string | null>(null);
  const [asking, setAsking] = useState<'accept' | 'reject' | null>(null);
  const target = choice === OTHER ? other : choice;
  const m = useMutation({
    mutationFn: async (a: 'accept' | 'reject'): Promise<unknown> => (a === 'accept'
      ? acceptSuggestions(g.item_code, target as string) : rejectSuggestions(g.item_code)),
    onSuccess: (_r, a) => {
      toast.success(t(`${K}.sug.done_${a}`));
      void qc.invalidateQueries({ queryKey: ['admin'] });
    },
    onError: (err) => toast.error(writeError(t, err)),
    onSettled: () => setAsking(null),
  });
  const path = target ? pathOf(tree.data?.nodes ?? [], target, i18n.language) : '';
  const name = g.item_name || g.item_code;
  const radio = `sug-${g.item_code}`;

  return (
    <li>
      <Card title={name} aside={<span className="text-sm font-semibold text-amber-900">{t(`${K}.sug.count`, { n: g.count })}</span>}>
        <p className="text-xs text-gray-500">
          <span className="font-mono" dir="ltr">{g.item_code}</span>
          {' · '}{t(`${K}.chains`, { n: g.chains_live ?? 0 })}{' · '}{fmtDate(g.latest_at)}
        </p>
        <p className="mt-1 text-sm text-gray-800 flex flex-wrap items-center gap-2">
          <span className="text-gray-500">{t(`${K}.item.current`)}:</span>
          <span dir="auto">{g.label?.path_he ?? t(`${K}.unlabeled`)}</span>
          <LabelChips label={g.label} />
        </p>

        <fieldset className="mt-3">
          <legend className="text-sm font-semibold text-gray-900 mb-1">{t(`${K}.sug.choose`)}</legend>
          <div className="space-y-1">
            {g.suggested.map(s => (
              <label key={s.category_id} className="flex items-center gap-2 min-h-[44px] text-sm cursor-pointer">
                <input type="radio" name={radio} value={s.category_id} checked={choice === s.category_id}
                  onChange={() => setChoice(s.category_id)} className="h-5 w-5" />
                <span dir="auto">{s.path_he || s.category_id}</span>
                <span className="text-xs font-semibold rounded-full bg-gray-100 border border-gray-300 px-2 py-0.5 tabular-nums">
                  ×{s.n}
                </span>
              </label>
            ))}
            <label className="flex items-center gap-2 min-h-[44px] text-sm cursor-pointer">
              <input type="radio" name={radio} value={OTHER} checked={choice === OTHER}
                onChange={() => setChoice(OTHER)} className="h-5 w-5" />
              {t(`${K}.sug.other`)}
            </label>
          </div>
        </fieldset>
        {choice === OTHER && (
          <div className="mt-2">
            {tree.isPending ? <Loading /> : tree.isError ? <ErrorBox error={tree.error} /> : (
              <CategoryPicker nodes={tree.data.nodes} value={other} onChange={setOther}
                currentId={g.label?.category_id} label={t(`${K}.sug.choose`)} maxHeightClass="max-h-56" />
            )}
          </div>
        )}

        <h3 className="text-sm font-semibold text-gray-900 mt-3 mb-1">{t(`${K}.sug.comments`)}</h3>
        {g.comments.length === 0 ? <p className="text-sm text-gray-500">{t(`${K}.sug.no_comments`)}</p> : (
          <ul className="space-y-1">
            {g.comments.map((c, k) => (
              <li key={k} className="text-sm rounded-lg bg-gray-50 border border-gray-200 p-2">
                <p className="line-clamp-2 break-words text-gray-900" dir="auto" title={c.text}>{c.text}</p>
                <p className="text-xs text-gray-500" dir="ltr">{c.category_id} · {fmtDate(c.at)}</p>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          <Button tone="primary" disabled={!target || m.isPending} onClick={() => setAsking('accept')}>
            <Check size={16} aria-hidden="true" /> {t(`${K}.sug.accept`)}
          </Button>
          <Button tone="danger" disabled={m.isPending} onClick={() => setAsking('reject')}>
            <X size={16} aria-hidden="true" /> {t(`${K}.sug.reject`)}
          </Button>
          <Button onClick={() => onOpen(g.item_code)}>{t(`${K}.open`)}</Button>
        </div>
      </Card>
      <ConfirmDialog
        open={asking !== null}
        message={asking === 'accept' ? t(`${K}.sug.confirm_accept`, { path, n: g.count })
          : t(`${K}.sug.confirm_reject`, { n: g.count })}
        tone={asking === 'reject' ? 'danger' : 'primary'}
        busy={m.isPending}
        onCancel={() => setAsking(null)}
        onConfirm={() => asking && m.mutate(asking)}
      />
    </li>
  );
}

export default function SuggestionsQueue({ onOpen }: { onOpen: (code: string) => void }) {
  const { t } = useTranslation();
  const q = useInfiniteQuery({
    queryKey: ['admin', 'cat-queue', 'suggestions'],
    queryFn: ({ pageParam }) => getCatQueue<SuggestionGroup>('suggestions', pageParam),
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
      <p className="text-xs text-gray-500 mb-3">
        {t(`${K}.queue_total`, { n: q.data.pages[0].total })} · {t(`${K}.sorted`)}
      </p>
      <ul className="space-y-3">{items.map(g => <Group key={g.item_code} g={g} onOpen={onOpen} />)}</ul>
      {q.hasNextPage && (
        <Button className="mt-4 w-full sm:w-auto" onClick={() => void q.fetchNextPage()} disabled={q.isFetchingNextPage}>
          {t('admin.common.load_more')}
        </Button>
      )}
    </div>
  );
}
