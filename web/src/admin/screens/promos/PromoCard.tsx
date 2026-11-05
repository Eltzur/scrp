import type { ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import Highlight from '../../../components/Highlight';
import type { PromoSummary } from '../../api';
import { fmtDate } from '../../format';
import { K } from './shared';
import { giftCouponView } from '../../../utils/giftCoupon';

function money(n: number) {
  return n.toFixed(2).replace(/\.00$/, '');
}

/** SU11A-62: where the promotion shows on the public promo lists, "מוצג ב-N
 *  ערים" with the list on expand, and a warning when it shows nowhere or not
 *  in checkCity (the city the admin checks against). */
function Coverage({ cities, checkCity }: { cities: string[]; checkCity?: string }) {
  const { t } = useTranslation();
  const missing = cities.length > 0 && checkCity && !cities.includes(checkCity);
  return (
    <div className="mt-2 text-xs">
      {cities.length === 0 ? (
        <p role="note" className="flex gap-1.5 items-start font-semibold text-rose-800">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" aria-hidden="true" /> {t(`${K}.coverage.none`)}
        </p>
      ) : (
        <details>
          <summary className="cursor-pointer min-h-[24px] text-gray-800 font-semibold">
            {cities.length === 1 ? t(`${K}.coverage.one`) : t(`${K}.coverage.many`, { n: cities.length })}
          </summary>
          <p className="mt-1 text-gray-700" dir="auto">{cities.join(' · ')}</p>
        </details>
      )}
      {missing && (
        <p role="note" className="mt-1 flex gap-1.5 items-start font-semibold text-amber-900">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" aria-hidden="true" /> {t(`${K}.coverage.not_in_city`, { city: checkCity })}
        </p>
      )}
    </div>
  );
}

/** The promotion as a card: chain, terms, reach, end date and one sample
 *  product. SU11A-62: with search text the sample is the best-matching
 *  product (term marked) plus the count of other matches; cities (when the
 *  API sent them) show the coverage. */
export default function PromoCard({ p, children, term, matches, checkCity }: {
  p: PromoSummary; children?: ReactNode; term?: string; matches?: number | null; checkCity?: string;
}) {
  const { t } = useTranslation();
  const s = p.sample;
  // SU11A-65: a gift coupon is "מתנה בקופון", the free quantity and the
  // condition; never "100% הנחה".
  const gift = s?.gift_coupon ? giftCouponView({ promo_description: p.promo_description, min_qty: s.min_qty }) : null;
  const terms = !s ? null
    : gift ? [t(`${K}.card.gift_coupon`), gift.qty != null ? t(`${K}.card.gift_qty`, { n: gift.qty }) : null, gift.condition]
      .filter(Boolean).join(' · ')
    : s.discount_price != null && s.min_qty != null && s.min_qty > 1 && s.min_qty <= 24
      ? t(`${K}.card.bundle`, { qty: Math.round(s.min_qty), price: money(s.discount_price) })
      : s.discount_price != null && s.discount_price > 0 ? t(`${K}.card.price`, { price: money(s.discount_price) })
        : s.discount_rate ? t(`${K}.card.rate`, { rate: s.discount_rate > 100 ? s.discount_rate / 100 : s.discount_rate })
          : null;
  const more = matches != null ? matches - 1 : 0;
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-semibold text-gray-900" dir="auto">{p.chain_name ?? p.chain_id}</p>
        <p className="text-xs text-gray-500 font-mono" dir="ltr">{t(`${K}.card.promo_id`, { id: p.promo_id })}</p>
      </div>
      <p className="mt-1 text-sm text-gray-900" dir="auto">
        {p.promo_description ? <Highlight text={p.promo_description} term={term} /> : '—'}
      </p>
      {s && (
        <p className="mt-1 text-xs text-gray-600" dir="auto">
          {t(term ? `${K}.card.match` : `${K}.card.sample`)}{' '}
          <span className="text-gray-900"><Highlight text={s.item_name || s.item_code} term={term} /></span>
          {terms && <> · <span className="font-semibold text-gray-800">{terms}</span></>}
          {more > 0 && <> · {t(`${K}.card.more_matches`, { n: more })}</>}
        </p>
      )}
      <p className="mt-1 text-xs text-gray-600">
        {t(`${K}.card.stores`, { n: p.stores })} · {t(`${K}.card.items`, { n: p.items })} ·{' '}
        {!p.live ? <span className="font-semibold text-rose-800">{t(`${K}.card.ended`)}</span>
          : p.promo_end ? t(`${K}.card.until`, { date: fmtDate(p.promo_end) }) : t(`${K}.card.no_end`)}
      </p>
      {p.cities && <Coverage cities={p.cities} checkCity={checkCity} />}
      {children}
    </div>
  );
}
