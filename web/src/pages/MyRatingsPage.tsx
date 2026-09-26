import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';
import { getMyRatings } from '../api/client';
import type { MyRatingRow } from '../api/client';
import { useAuth } from '../components/AuthContext';
import RatingForm from '../components/RatingForm';

/**
 * "הדירוגים שלי" — the signed-in user's own reviews.
 *
 * Auth-required with the same redirect FavoritesPage uses. Lists ACTIVE and
 * HELD reviews: an author must be able to see and edit a review that is under
 * moderation, or it looks deleted and they post a duplicate. A held review is
 * tagged "בבדיקה" — honest that it is not live, and never says WHY, because
 * that would tell a flagged author which word tripped the filter.
 *
 * Editing reuses RatingForm — the same component the modal's reviews tab uses
 * — rather than duplicating the X/XX/XXX scale.
 */

const GLYPH: Record<number, string> = { 1: 'X', 2: 'XX', 3: 'XXX' };
const LEVEL_KEY: Record<number, string> = {
  1: 'ratings.level1',
  2: 'ratings.level2',
  3: 'ratings.level3',
};

export default function MyRatingsPage() {
  const { t }                             = useTranslation();
  const { user, isLoading: authLoading }  = useAuth();
  const navigate                          = useNavigate();

  const [rows, setRows]       = useState<MyRatingRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<string | null>(null);

  useEffect(() => {
    if (!authLoading && !user) navigate('/login');
  }, [user, authLoading, navigate]);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      setRows(await getMyRatings());
    } catch {
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { void load(); }, [load]);

  if (authLoading || !user) return null;

  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">
      <div className="max-w-2xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-xl font-bold text-gray-900">{t('ratings.my_title')}</h1>
          <Link to="/" className="text-sm text-emerald-700 hover:underline">
            ← {t('app.title')}
          </Link>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="animate-spin text-gray-400" size={22} aria-hidden="true" />
            <span className="sr-only">{t('load_more.loading')}</span>
          </div>
        ) : !rows || rows.length === 0 ? (
          <div className="text-center py-12 space-y-1">
            <p className="text-gray-700 font-medium">{t('ratings.my_empty')}</p>
            <p className="text-gray-500 text-sm">{t('ratings.my_empty_hint')}</p>
          </div>
        ) : (
          <ul className="space-y-3">
            {rows.map(r => {
              const held   = r.status !== 'active';
              const isOpen = editing === r.item_code;
              return (
                <li
                  key={r.id}
                  className="bg-white rounded-xl border border-gray-200 p-4 space-y-2"
                >
                  <div className="flex items-start gap-2">
                    <span className="font-bold text-emerald-700">{GLYPH[r.rating]}</span>
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-gray-900 text-sm" dir="auto">
                        {r.item_name ?? r.item_code}
                      </p>
                      <p className="text-xs text-gray-500">{t(LEVEL_KEY[r.rating])}</p>
                    </div>
                    {held && (
                      <span className="shrink-0 px-2 py-0.5 rounded-full bg-amber-100 text-amber-700
                                       text-[11px] font-bold">
                        {t('ratings.status_held')}
                      </span>
                    )}
                  </div>

                  {r.comment && (
                    <p className="text-sm text-gray-800 whitespace-pre-wrap" dir="auto">
                      {r.comment}
                    </p>
                  )}

                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] text-gray-400 font-mono" dir="ltr">{r.item_code}</p>
                    <button
                      type="button"
                      onClick={() => setEditing(isOpen ? null : r.item_code)}
                      aria-expanded={isOpen}
                      className="text-xs font-semibold text-emerald-700 hover:underline
                                 focus:outline-none focus:ring-2 focus:ring-emerald-500 rounded px-1"
                    >
                      {isOpen ? t('ratings.cancel') : t('ratings.your_rating')}
                    </button>
                  </div>

                  {isOpen && (
                    <div className="pt-2 border-t border-gray-100">
                      <RatingForm
                        itemCode={r.item_code}
                        initialRating={r.rating}
                        initialComment={r.comment}
                        onSaved={() => { setEditing(null); void load(); }}
                      />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
