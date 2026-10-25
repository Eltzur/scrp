import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Loader2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import {
  acceptTerms, apiErrorCode, getCategoryTree, getMyTerms, suggestCategory, type ItemCategory,
} from '../../api/client';
import { TERMS_VERSION } from '../../legal/terms';
import CategoryPicker from './CategoryPicker';
import './strings';

/**
 * "הצעת עדכון קטגוריה" (SU11A-57), a lazy chunk opened from CategoryLine for
 * signed-in users: current path, searchable picker, optional comment (200),
 * submit. The terms consent works as in RatingForm: a user who has not accepted
 * the current terms ticks the box here and the submit records it first.
 *
 * Error answers are shown in the dialog: terms_required (the consent box),
 * daily_limit, already_suggested, account_banned, same / invalid category.
 * A comment the blacklist withholds still answers 201: same thanks as any other.
 *
 * Native <dialog>: focus trap and Esc from the browser. Esc is stopped here so
 * the product dialog underneath (which listens on document) stays open.
 */
const COMMENT_MAX = 200;
const ERRORS: Record<string, string> = {
  daily_limit: 'category.err_daily_limit',
  already_suggested: 'category.err_already',
  account_banned: 'ratings.account_banned',
  same_category: 'category.err_same',
  invalid_category: 'category.err_invalid',
  item_not_found: 'category.err_invalid',
  login_required: 'category.registered_only',
};

interface Props { itemCode: string; current: ItemCategory | null; onClose: () => void }

export default function CategorySuggestDialog({ itemCode, current, onClose }: Props) {
  const { t, i18n } = useTranslation();
  const ref = useRef<HTMLDialogElement>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [termsRequired, setTermsRequired] = useState<boolean | null>(null);
  const [agreed, setAgreed] = useState(false);
  const tree = useQuery({ queryKey: ['category-tree'], queryFn: getCategoryTree, staleTime: 60 * 60 * 1000, retry: 1 });

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
    return () => { if (d?.open) d.close(); };
  }, []);

  useEffect(() => {
    let active = true;
    getMyTerms()
      .then(s => { if (active) setTermsRequired(s.required); })
      .catch(() => { if (active) setTermsRequired(null); });
    return () => { active = false; };
  }, []);

  const en = i18n.language.startsWith('en');
  const currentPath = (current?.path ?? []).map(p => (en && p.name_en ? p.name_en : p.name_he)).join(' › ');
  // A partial (low-confidence) label only names the department: nothing to grey out.
  const currentId = current && !current.partial ? current.category_id : null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!picked || sending || (termsRequired && !agreed)) return;
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
      await suggestCategory(itemCode, { category_id: picked, comment: comment.trim() || null });
      toast.success(t('category.thanks'));
      onClose();
    } catch (err) {
      const code = apiErrorCode(err);
      if (code === 'terms_required') {
        setTermsRequired(true);
        setAgreed(false);
        setError(t('category.consent_title'));
      } else if (code && ERRORS[code]) {
        setError(t(ERRORS[code]));
      } else {
        setError(t('category.err_failed'));
      }
    } finally {
      setSending(false);
    }
  };

  const linkClass = 'text-emerald-700 font-semibold underline focus:outline-none ' +
    'focus-visible:ring-2 focus-visible:ring-emerald-500 rounded';

  return (
    <dialog
      ref={ref}
      aria-labelledby="cat-suggest-title"
      onCancel={(e) => { e.preventDefault(); if (!sending) onClose(); }}
      onKeyDown={(e) => { if (e.key === 'Escape') e.stopPropagation(); }}
      className="rounded-2xl p-0 w-[min(94vw,32rem)] max-h-[90vh] backdrop:bg-black/50"
      dir={en ? 'ltr' : 'rtl'}
    >
      <form onSubmit={submit} className="flex flex-col max-h-[90vh]">
        <div className="flex items-start justify-between gap-3 p-4 border-b border-gray-100">
          <h2 id="cat-suggest-title" className="text-base font-bold text-gray-900">{t('category.dialog_title')}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('category.close')}
            className="shrink-0 min-h-[44px] min-w-[44px] -m-2 inline-flex items-center justify-center rounded-lg
              text-gray-500 hover:text-gray-800 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="overflow-y-auto p-4 space-y-4">
          <p className="text-sm text-gray-700">
            <span className="font-semibold">{t('category.current')}: </span>
            <span dir="auto">{currentPath || t('category.none')}</span>
          </p>

          {tree.isPending ? (
            <p className="flex items-center gap-2 text-sm text-gray-600" role="status">
              <Loader2 size={16} className="animate-spin" aria-hidden="true" /> {t('category.loading')}
            </p>
          ) : tree.isError ? (
            <p role="alert" className="text-sm text-rose-700">{t('category.err_tree')}</p>
          ) : (
            <CategoryPicker
              nodes={tree.data.nodes}
              value={picked}
              onChange={setPicked}
              currentId={currentId}
              label={t('category.picker_label')}
              maxHeightClass="max-h-64"
            />
          )}

          <div>
            <label htmlFor="cat-suggest-comment" className="block text-sm font-semibold text-gray-800 mb-1">
              {t('category.comment_label')}
            </label>
            <textarea
              id="cat-suggest-comment"
              value={comment}
              onChange={e => setComment(e.target.value)}
              maxLength={COMMENT_MAX}
              rows={2}
              dir="auto"
              aria-describedby="cat-suggest-count"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm resize-y
                focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
            />
            <p id="cat-suggest-count" className="text-xs text-gray-500 text-end">
              {t('category.comment_count', { n: comment.length, max: COMMENT_MAX })}
            </p>
          </div>

          {termsRequired && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 space-y-2">
              <p className="text-sm font-semibold text-gray-900">{t('category.consent_title')}</p>
              <div className="flex items-start gap-2">
                <input
                  id="cat-suggest-terms"
                  type="checkbox"
                  required
                  checked={agreed}
                  onChange={e => setAgreed(e.target.checked)}
                  className="mt-0.5 h-5 w-5 shrink-0 rounded border-gray-400
                    focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
                />
                <label htmlFor="cat-suggest-terms" className="text-sm text-gray-800 leading-snug">
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
        </div>

        <div className="p-4 border-t border-gray-100 flex gap-2 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="min-h-[44px] px-4 rounded-xl border border-gray-300 text-sm font-semibold text-gray-900
              hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
          >
            {t('category.cancel')}
          </button>
          <button
            type="submit"
            disabled={!picked || sending || (termsRequired === true && !agreed)}
            aria-busy={sending}
            className="min-h-[44px] px-4 rounded-xl bg-emerald-700 text-white text-sm font-semibold
              hover:bg-emerald-800 disabled:opacity-60 disabled:cursor-not-allowed
              focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-emerald-500
              inline-flex items-center gap-2"
          >
            {sending && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
            {t('category.submit')}
          </button>
        </div>
      </form>
    </dialog>
  );
}
