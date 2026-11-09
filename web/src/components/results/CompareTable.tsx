import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CheckCircle2 } from 'lucide-react';
import clsx from 'clsx';
import type { ProductWithPrices } from '../../api/client';
import { useChains } from '../../api/hooks';
import { K } from './strings';
import { QuotePrice } from './ResultsListView';
import { formatIls, productDisplayName } from '../../utils/priceDisplay';
import {
  TABLE_MAX_COLUMNS, chainTotals, loadChains, pageChains, quoteByChain, rowCheapest, saveChains,
  tableColumns, toggleColumn,
} from '../../utils/resultViews';

interface Props {
  items: ProductWithPrices[];
  /** The selected city; null = nationwide (the cell is the chain's lowest price anywhere). */
  city: string | null;
}

/**
 * SU11A-72: products (rows, the page in list order) × chains (columns). A cell
 * is the chain's price at its cheapest branch in the selected city - exactly
 * the per-chain quote the search / category request already returned.
 */
export default function CompareTable({ items, city }: Props) {
  const { t, i18n } = useTranslation();
  const lang = i18n.language;
  const { data: allChains = [] } = useChains();
  const [remembered, setRemembered] = useState<string[]>(() => loadChains());
  const cols = useMemo(() => tableColumns(items, remembered), [items, remembered]);
  const [limitNote, setLimitNote] = useState(false);

  const onPage = useMemo(() => pageChains(items), [items]);
  const names = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of allChains) m.set(c.chain_id, c.name ?? c.chain_id);
    for (const c of onPage) if (!m.has(c.chain_id)) m.set(c.chain_id, c.name);
    return m;
  }, [allChains, onPage]);
  const chips = useMemo(() => {
    const carried = new Map(onPage.map(c => [c.chain_id, c.carried]));
    return [...names.keys()].sort((a, b) =>
      (carried.get(b) ?? 0) - (carried.get(a) ?? 0) || (names.get(a) ?? '').localeCompare(names.get(b) ?? '', 'he'));
  }, [names, onPage]);

  const toggle = (id: string) => {
    const next = toggleColumn(cols, id);
    setLimitNote(next === cols && !cols.includes(id) && cols.length >= TABLE_MAX_COLUMNS);
    if (next !== cols) { setRemembered(next); saveChains(next); }
  };

  const totals = chainTotals(items, cols);
  const anyComplete = totals.some(x => x.winner);
  const nameOf = (id: string) => names.get(id) ?? id;

  return (
    <div>
      <fieldset className="mb-3">
        <legend className="text-sm font-medium text-gray-800 mb-1.5">{t(`${K}.chips_label`)}</legend>
        <div className="flex flex-wrap gap-2">
          {chips.map(id => {
            const on = cols.includes(id);
            return (
              <button
                key={id}
                type="button"
                aria-pressed={on}
                onClick={() => toggle(id)}
                className={clsx(
                  'min-h-[32px] px-3 rounded-full border text-sm font-medium',
                  'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700',
                  on ? 'bg-emerald-700 border-emerald-700 text-white' : 'bg-white border-gray-500 text-gray-800 hover:border-emerald-700',
                )}
              >
                {on && <CheckCircle2 size={13} aria-hidden="true" className="inline me-1 -mt-0.5" />}
                {nameOf(id)}
              </button>
            );
          })}
        </div>
        {limitNote && <p role="status" className="mt-1.5 text-xs text-gray-700">{t(`${K}.max_chains`)}</p>}
      </fieldset>

      <p className="text-xs text-gray-700 mb-2">
        {city ? t(`${K}.city_note`, { city }) : t(`${K}.no_city_note`)} {t(`${K}.promo_note`)}
      </p>

      <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white" tabIndex={0} role="region"
           aria-label={t(`${K}.table_caption`, { count: items.length })}>
        <table className="min-w-full border-collapse text-sm">
          <caption className="sr-only">{t(`${K}.table_caption`, { count: items.length })}</caption>
          <thead>
            <tr className="bg-gray-50">
              <th scope="col" className="sticky start-0 z-10 bg-gray-50 px-3 py-2 text-start font-semibold text-gray-900 min-w-[10rem] border-b border-gray-200">
                {t(`${K}.product_col`)}
              </th>
              {cols.map(c => (
                <th key={c} scope="col" className="px-3 py-2 text-center font-semibold text-gray-900 whitespace-nowrap border-b border-gray-200">
                  {nameOf(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map(it => {
              const by = quoteByChain(it);
              const best = rowCheapest(it, cols);
              return (
                <tr key={it.product.item_code} className="border-b border-gray-100">
                  <th scope="row" className="sticky start-0 z-10 bg-white px-3 py-2 text-start font-medium text-gray-900 min-w-[10rem] max-w-[16rem]">
                    <span dir="auto" className="line-clamp-2">{productDisplayName(it.product)}</span>
                  </th>
                  {cols.map(c => {
                    const q = by.get(c);
                    if (!q) {
                      return (
                        <td key={c} className="px-3 py-2 text-center text-gray-700">
                          <span aria-hidden="true">—</span><span className="sr-only">{t(`${K}.not_sold`)}</span>
                        </td>
                      );
                    }
                    const win = best.has(c);
                    return (
                      <td key={c} className={clsx('px-3 py-2 text-center whitespace-nowrap', win && 'bg-emerald-50')}>
                        <span className="inline-flex items-center gap-1">
                          {win && <CheckCircle2 size={12} aria-hidden="true" className="text-emerald-800" />}
                          <QuotePrice q={q} cheapest={win} lang={lang} />
                        </span>
                        {win && <span className="sr-only">, {t(`${K}.cheapest`)}</span>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="bg-gray-50">
              <th scope="row" className="sticky start-0 z-10 bg-gray-50 px-3 py-2 text-start font-semibold text-gray-900">
                {t(`${K}.total_row`)}
              </th>
              {totals.map(x => (
                <td key={x.chain_id} className={clsx('px-3 py-2 text-center whitespace-nowrap', x.winner && 'bg-emerald-100')}>
                  {x.missing === items.length ? (
                    // sells none of the listed products: no ₪0.00 "total"
                    <><span aria-hidden="true">—</span><span className="sr-only">{t(`${K}.not_sold`)}</span></>
                  ) : (
                    <span dir="ltr" className={clsx('font-bold tabular-nums', x.winner ? 'text-emerald-900' : 'text-gray-900')}>
                      {formatIls(x.total, lang)}
                    </span>
                  )}
                  {x.missing > 0 && (
                    <span className="block text-xs font-medium text-amber-900">{t(`${K}.missing`, { count: x.missing })}</span>
                  )}
                  {x.winner && (
                    <span className="block text-xs font-semibold text-emerald-900">
                      <CheckCircle2 size={12} aria-hidden="true" className="inline me-1 -mt-0.5" />
                      {t(`${K}.cheapest_total`)}
                    </span>
                  )}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
      {!anyComplete && items.length > 0 && <p className="mt-2 text-xs text-gray-700">{t(`${K}.no_complete`)}</p>}
    </div>
  );
}
