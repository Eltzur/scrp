import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BarChart3 } from 'lucide-react';
import clsx from 'clsx';
import { getRatings } from '../api/client';

/**
 * Compact rating summary for a product card: "73% · 12 דירוגים".
 *
 * Logic and wording match the mobile card exactly (xxl-super-mobile
 * components/rating-summary.tsx):
 *   - count === 0 shows the neutral "אין דירוגים עדיין", never 0% — zero would
 *     read as a unanimously terrible product rather than an unrated one;
 *   - a FAILED fetch lands in that same neutral state, so ratings can never
 *     take the price card down with them.
 *
 * One request per card. Batching would need a bulk endpoint, which does not
 * exist today — noted rather than pre-built.
 */
export default function RatingBadge({
  itemCode,
  onOpen,
}: {
  itemCode: string;
  /** Opens the product modal directly on its reviews tab. */
  onOpen: () => void;
}) {
  const { t } = useTranslation();
  const [state, setState] = useState<{ pct: number | null; count: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRatings(itemCode)
      .then(r => { if (!cancelled) setState({ pct: r.average_pct, count: r.count }); })
      .catch(() => { if (!cancelled) setState({ pct: null, count: 0 }); });
    return () => { cancelled = true; };
  }, [itemCode]);

  const rated = state != null && state.count > 0 && state.pct != null;
  const label = rated
    ? t('ratings.summary', { pct: Math.round(state!.pct!), count: state!.count })
    : t('ratings.none');

  return (
    <button
      type="button"
      onClick={e => { e.stopPropagation(); onOpen(); }}
      aria-label={`${t('ratings.title')}: ${label}`}
      className={clsx(
        'inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium border transition-colors',
        'focus:outline-none focus:ring-2 focus:ring-emerald-500',
        rated
          ? 'text-emerald-700 border-emerald-200 bg-emerald-50 hover:bg-emerald-100'
          : 'text-gray-500 border-gray-200 bg-white hover:bg-gray-50',
      )}
    >
      <BarChart3 size={11} aria-hidden="true" />
      <span>{label}</span>
    </button>
  );
}
