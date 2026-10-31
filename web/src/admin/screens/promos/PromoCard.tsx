import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { PromoSummary } from '../../api';
import { fmtDate } from '../../format';
import { K } from './shared';

function money(n: number) {
  return n.toFixed(2).replace(/\.00$/, '');
}

/** The promotion as a card: chain, terms, reach, end date and one sample product. */
export default function PromoCard({ p, children }: { p: PromoSummary; children?: ReactNode }) {
  const { t } = useTranslation();
  const s = p.sample;
  const terms = !s ? null
    : s.discount_price != null && s.min_qty != null && s.min_qty > 1 && s.min_qty <= 24
      ? t(`${K}.card.bundle`, { qty: Math.round(s.min_qty), price: money(s.discount_price) })
      : s.discount_price != null && s.discount_price > 0 ? t(`${K}.card.price`, { price: money(s.discount_price) })
        : s.discount_rate ? t(`${K}.card.rate`, { rate: s.discount_rate > 100 ? s.discount_rate / 100 : s.discount_rate })
          : null;
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-semibold text-gray-900" dir="auto">{p.chain_name ?? p.chain_id}</p>
        <p className="text-xs text-gray-500 font-mono" dir="ltr">{t(`${K}.card.promo_id`, { id: p.promo_id })}</p>
      </div>
      <p className="mt-1 text-sm text-gray-900" dir="auto">{p.promo_description || '—'}</p>
      {s && (
        <p className="mt-1 text-xs text-gray-600" dir="auto">
          {t(`${K}.card.sample`, { name: s.item_name || s.item_code })}
          {terms && <> · <span className="font-semibold text-gray-800">{terms}</span></>}
        </p>
      )}
      <p className="mt-1 text-xs text-gray-600">
        {t(`${K}.card.stores`, { n: p.stores })} · {t(`${K}.card.items`, { n: p.items })} ·{' '}
        {!p.live ? <span className="font-semibold text-rose-800">{t(`${K}.card.ended`)}</span>
          : p.promo_end ? t(`${K}.card.until`, { date: fmtDate(p.promo_end) }) : t(`${K}.card.no_end`)}
      </p>
      {children}
    </div>
  );
}
