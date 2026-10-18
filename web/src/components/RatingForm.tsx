import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import clsx from 'clsx';
import { acceptTerms, apiErrorCode, getMyTerms, submitRating } from '../api/client';
import { TERMS_VERSION } from '../legal/terms';
import { useAuth } from './AuthContext';

/**
 * The X / XX / XXX rating form.
 *
 * Shared by ProductDetailModal's reviews tab and MyRatingsPage, so the scale,
 * the copy and the submit behaviour exist once. Deliberately NOT a star widget:
 * the backend scale is 1-3 with named levels, and mobile already ships this
 * exact visual language (xxl-super-mobile product-detail.tsx). Hebrew labels
 * are taken verbatim from mobile's he.ts.
 *
 * SU11A-44: a user with no consent to the current terms (GET /me/terms says
 * `required`; e.g. signed up before the consent checkbox existed) sees a required
 * checkbox here, and the submit first records it (POST /me/terms). The server can
 * also answer 403 terms_required (RATINGS_REQUIRE_TERMS) or account_banned.
 */

const LEVELS = [
  { value: 1, glyph: 'X',   key: 'ratings.level1' },
  { value: 2, glyph: 'XX',  key: 'ratings.level2' },
  { value: 3, glyph: 'XXX', key: 'ratings.level3' },
] as const;

interface Props {
  itemCode: string;
  /** Existing rating to edit, if the user already has one for this item. */
  initialRating?: number | null;
  initialComment?: string | null;
  /** Called after a successful submit so the caller can refresh its data. */
  onSaved?: () => void;
}

export default function RatingForm({
  itemCode,
  initialRating = null,
  initialComment = null,
  onSaved,
}: Props) {
  const { t }    = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();

  const [picked,  setPicked]  = useState<number | null>(initialRating);
  const [comment, setComment] = useState(initialComment ?? '');
  const [sending, setSending] = useState(false);
  // null = unknown (not loaded or failed): no checkbox, the server decides.
  const [termsRequired, setTermsRequired] = useState<boolean | null>(null);
  const [agreed,  setAgreed]  = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  // The caller may resolve the existing rating asynchronously (GET /me/ratings),
  // so adopt it when it lands rather than only on first mount.
  useEffect(() => { setPicked(initialRating); },          [initialRating]);
  useEffect(() => { setComment(initialComment ?? ''); },  [initialComment]);

  useEffect(() => {
    // Signed out the form is not rendered, so a stale value does no harm.
    if (!user) return;
    let active = true;
    getMyTerms()
      .then(s => { if (active) setTermsRequired(s.required); })
      .catch(() => { if (active) setTermsRequired(null); });
    return () => { active = false; };
  }, [user]);

  const isEdit = initialRating != null;

  // Signed out: ratings and comments stay visible, the form does not. Same
  // gating Favorites already uses — a prompt that routes to /login.
  if (!user) {
    return (
      <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-center space-y-2">
        <p className="text-sm text-gray-600">{t('ratings.sign_in_prompt')}</p>
        <button
          type="button"
          onClick={() => navigate('/login')}
          className="px-4 py-2 rounded-lg bg-emerald-700 text-white text-sm font-semibold
                     hover:bg-emerald-800 transition-colors"
        >
          {t('ratings.sign_in_cta')}
        </button>
      </div>
    );
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (picked == null || sending) return;
    if (termsRequired && !agreed) return;
    setSending(true);
    setError(null);
    try {
      if (termsRequired) {
        try {
          await acceptTerms(TERMS_VERSION);
        } catch {
          setError(t('ratings.terms_failed'));
          return;
        }
        setTermsRequired(false);
      }
      // The response carries `blocked`, which is DELIBERATELY IGNORED. A
      // blacklisted submission returns 200 and must look identical to any
      // other success — telling the author would teach them which word tripped
      // the filter. Do not add a branch here.
      await submitRating(itemCode, { rating: picked, comment: comment.trim() || null });
      toast.success(t('ratings.saved'));
      onSaved?.();
    } catch (err) {
      const code = apiErrorCode(err);
      if (code === 'account_banned') {
        setError(t('ratings.account_banned'));
      } else if (code === 'terms_required') {
        setTermsRequired(true);
        setAgreed(false);
        setError(t('ratings.consent_title'));
      } else {
        toast.error(t('ratings.failed'));
      }
    } finally {
      setSending(false);
    }
  };

  const linkClass = 'text-emerald-700 font-semibold underline focus:outline-none ' +
    'focus-visible:ring-2 focus-visible:ring-emerald-500 rounded';

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <fieldset>
        <legend className="text-sm font-semibold text-gray-800 mb-2">
          {isEdit ? t('ratings.your_rating') : t('ratings.scale_title')}
        </legend>
        {/* radiogroup rather than buttons: this is a single-choice control, and
            arrow-key navigation between options is what a screen-reader user
            expects. Native radios keep that for free. */}
        <div className="flex gap-2">
          {LEVELS.map(l => {
            const on = picked === l.value;
            return (
              <label
                key={l.value}
                className={clsx(
                  'flex-1 cursor-pointer rounded-xl border p-3 text-center transition-colors',
                  'focus-within:ring-2 focus-within:ring-emerald-500 focus-within:ring-offset-1',
                  on
                    ? 'border-2 border-emerald-600 bg-emerald-50'
                    : 'border-gray-300 hover:border-emerald-300',
                )}
              >
                <input
                  type="radio"
                  name={`rating-${itemCode}`}
                  value={l.value}
                  checked={on}
                  onChange={() => setPicked(l.value)}
                  className="sr-only"
                />
                <span className={clsx('block text-lg font-bold',
                  on ? 'text-emerald-700' : 'text-gray-700')}>
                  {l.glyph}
                </span>
                <span className="block text-[11px] text-gray-500 mt-0.5">{t(l.key)}</span>
              </label>
            );
          })}
        </div>
      </fieldset>

      <div>
        <label htmlFor={`comment-${itemCode}`} className="sr-only">
          {t('ratings.comment_placeholder')}
        </label>
        <textarea
          id={`comment-${itemCode}`}
          value={comment}
          onChange={e => setComment(e.target.value)}
          placeholder={t('ratings.comment_placeholder')}
          maxLength={2000}
          rows={3}
          dir="auto"
          className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-y
                     focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
        />
      </div>

      {termsRequired && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 space-y-2">
          <p className="text-sm font-semibold text-gray-900">{t('ratings.consent_title')}</p>
          <div className="flex items-start gap-2">
            <input
              id={`terms-${itemCode}`}
              type="checkbox"
              required
              checked={agreed}
              onChange={e => setAgreed(e.target.checked)}
              className="mt-0.5 h-5 w-5 shrink-0 rounded border-gray-400
                         focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
            />
            <label htmlFor={`terms-${itemCode}`} className="text-sm text-gray-800 leading-snug">
              {t('ratings.consent_before')}{' '}
              <a href="/disclaimer" target="_blank" rel="noopener noreferrer" className={linkClass}>
                {t('ratings.consent_terms')}
              </a>
              {' '}{t('ratings.consent_and')}{' '}
              <a href="/privacy" target="_blank" rel="noopener noreferrer" className={linkClass}>
                {t('ratings.consent_privacy')}
              </a>
              {' '}{t('ratings.consent_after')}
            </label>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={picked == null || sending || (termsRequired === true && !agreed)}
        className="w-full py-2.5 bg-emerald-700 text-white rounded-xl text-sm font-semibold
                   hover:bg-emerald-800 disabled:opacity-60 disabled:cursor-not-allowed
                   transition-colors"
      >
        {sending ? t('ratings.sending') : isEdit ? t('ratings.update') : t('ratings.submit')}
      </button>
    </form>
  );
}
