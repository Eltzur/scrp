import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Flag } from 'lucide-react';
import { toast } from 'sonner';
import { getMyRatings, getRatings, reportRating } from '../api/client';
import type { RatingOut, RatingsResponse } from '../api/client';
import { useAuth } from './AuthContext';
import RatingForm from './RatingForm';

/**
 * Reviews tab contents: aggregate, comment list, report action, submit form.
 *
 * Comments carry NO author identifier — the public endpoint is anonymous and
 * returns {id, rating, comment, created_at, updated_at}. They are therefore
 * displayed anonymously because there is nothing to attribute them to, not as
 * a privacy choice.
 */

const GLYPH: Record<number, string> = { 1: 'X', 2: 'XX', 3: 'XXX' };
const LEVEL_KEY: Record<number, string> = {
  1: 'ratings.level1',
  2: 'ratings.level2',
  3: 'ratings.level3',
};

function formatWhen(iso: string, lang: string): string {
  // The API formats timestamps with Postgres to_char(... 'OF'), which omits the
  // minutes on a whole-hour offset ("+03"). That is not valid ISO 8601 and
  // Date parses it as Invalid Date — the same bug already fixed on mobile.
  const repaired = iso.replace(/([+-]\d{2})$/, '$1:00');
  const d = new Date(repaired);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleDateString(lang, { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function ReviewsPanel({ itemCode }: { itemCode: string }) {
  const { t, i18n } = useTranslation();
  const { user }    = useAuth();

  const [data, setData]   = useState<RatingsResponse | null>(null);
  const [mine, setMine]   = useState<{ rating: number; comment: string | null } | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await getRatings(itemCode));
      setFailed(false);
    } catch {
      // Ratings are supplementary — a failure degrades to the neutral empty
      // state rather than breaking the modal.
      setFailed(true);
    }
  }, [itemCode]);

  useEffect(() => { void load(); }, [load]);

  // Pre-fill from the caller's own ratings. /me/ratings exists precisely for
  // this, so no local workaround is needed (mobile's first pass predated it).
  const loadMine = useCallback(async () => {
    if (!user) { setMine(null); return; }
    try {
      const rows = await getMyRatings();
      const row  = rows.find(r => r.item_code === itemCode);
      setMine(row ? { rating: row.rating, comment: row.comment } : null);
    } catch {
      setMine(null);
    }
  }, [user, itemCode]);

  useEffect(() => { void loadMine(); }, [loadMine]);

  const handleReport = async (row: RatingOut) => {
    if (!user) { toast(t('ratings.report_sign_in')); return; }
    const reason = window.prompt(t('ratings.report_placeholder')) ?? null;
    try {
      await reportRating(row.id, reason);
      toast.success(t('ratings.reported'));
    } catch {
      toast.error(t('ratings.report_failed'));
    }
  };

  const count    = data?.count ?? 0;
  const pct      = data?.average_pct;
  const comments = (data?.ratings ?? []).filter(r => r.comment && r.comment.trim());
  const hasAggregate = !failed && count > 0 && pct != null;

  return (
    <div className="flex flex-col gap-5">
      {/* Aggregate */}
      <div className="rounded-xl bg-gray-50 border border-gray-100 p-4 text-center">
        {hasAggregate ? (
          <>
            <p className="text-3xl font-bold text-emerald-700">{Math.round(pct!)}%</p>
            <p className="text-xs text-gray-500 mt-0.5">
              {t('ratings.count_only', { count })}
            </p>
          </>
        ) : (
          <p className="text-sm text-gray-500">{t('ratings.none')}</p>
        )}
      </div>

      {/* Submit / edit */}
      <RatingForm
        itemCode={itemCode}
        initialRating={mine?.rating ?? null}
        initialComment={mine?.comment ?? null}
        onSaved={() => { void load(); void loadMine(); }}
      />

      {/* Comments */}
      <section>
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
          {t('ratings.comments_title')}
        </h4>
        {comments.length === 0 ? (
          <p className="text-sm text-gray-500">{t('ratings.no_comments')}</p>
        ) : (
          <ul className="space-y-2">
            {comments.map(r => (
              <li key={r.id} className="rounded-lg bg-gray-50 border border-gray-100 p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-bold text-emerald-700 text-sm">{GLYPH[r.rating]}</span>
                  <span className="text-xs text-gray-500">{t(LEVEL_KEY[r.rating])}</span>
                  <span className="flex-1" />
                  <span className="text-[11px] text-gray-400">
                    {formatWhen(r.updated_at, i18n.language)}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleReport(r)}
                    aria-label={t('ratings.report')}
                    title={t('ratings.report')}
                    className="p-1 rounded text-gray-400 hover:text-rose-600 hover:bg-rose-50
                               focus:outline-none focus:ring-2 focus:ring-rose-400 transition-colors"
                  >
                    <Flag size={13} aria-hidden="true" />
                  </button>
                </div>
                <p className="text-sm text-gray-800 whitespace-pre-wrap" dir="auto">{r.comment}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
