import { lazy, Suspense, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Tag } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { getItemCategory, type ItemCategory } from '../api/client';
import { useAuth } from './AuthContext';

/**
 * The item's category path and the "הצעת עדכון קטגוריה" button (SU11A-57),
 * in the product dialog's shared header. Small on purpose: the picker dialog is
 * a lazy chunk, loaded on the first tap.
 *
 * A low-confidence label arrives as its department only (the API cuts it).
 * The block has a fixed height whatever the state, so loading the path moves
 * nothing. Signed out, the button opens a note with sign-in / sign-up links
 * instead of the dialog.
 */
const CategorySuggestDialog = lazy(() => import('./category/CategorySuggestDialog'));

export default function CategoryLine({ itemCode }: { itemCode: string }) {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const [cat, setCat] = useState<ItemCategory | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState(false);

  useEffect(() => {
    let active = true;
    getItemCategory(itemCode)
      .then(c => { if (active) setCat(c); })
      .catch(() => { if (active) setCat(null); })
      .finally(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, [itemCode]);

  const en = i18n.language.startsWith('en');
  const path = (cat?.path ?? []).map(p => (en && p.name_en ? p.name_en : p.name_he)).join(' › ');
  const noteId = `cat-note-${itemCode}`;

  return (
    <div className="text-xs text-gray-600">
      <div className="flex items-center justify-center gap-1.5 min-h-[20px]">
        <Tag size={12} className="shrink-0 text-gray-500" aria-hidden="true" />
        <span className="truncate" dir="auto">
          {!loaded ? <span className="text-gray-400">{t('category.loading')}</span>
            : path ? <><span className="sr-only">{t('category.label')}: </span>{path}</>
              : t('category.none')}
        </span>
      </div>
      <div className="flex justify-center">
        <button
          type="button"
          onClick={() => (user ? setOpen(true) : setNote(v => !v))}
          aria-expanded={user ? undefined : note}
          aria-controls={user ? undefined : noteId}
          aria-haspopup={user ? 'dialog' : undefined}
          className="min-h-[44px] px-3 text-sm font-semibold text-emerald-700 underline-offset-2 hover:underline
            rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        >
          {t('category.suggest_button')}
        </button>
      </div>
      {!user && note && (
        <p id={noteId} role="status" className="text-center text-sm text-gray-700 pb-1">
          {t('category.registered_only')}{' '}
          <Link to="/login" className="font-semibold text-emerald-700 underline">{t('category.sign_in')}</Link>
          {' · '}
          <Link to="/signup" className="font-semibold text-emerald-700 underline">{t('category.sign_up')}</Link>
        </p>
      )}
      {open && (
        <Suspense fallback={null}>
          <CategorySuggestDialog itemCode={itemCode} current={cat} onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </div>
  );
}
