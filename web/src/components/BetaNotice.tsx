import { useCallback, useEffect, useId, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { X } from 'lucide-react';
import { COOKIE_CHOICE_EVENT } from '../utils/analytics';
import { isAdminHostname } from '../utils/hostname';
import { NOTICE_OPEN_EVENT, markNoticeSeen, shouldAutoShow } from '../utils/betaNotice';

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';
const FOCUS_RING = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700';

/**
 * SU11A-75: the "בהרצה" notice. A modal dialog: focus goes to "הבנתי" and
 * returns to where it was on close; Tab stays inside; Esc, the X, a backdrop
 * click and "הבנתי" all close it (and mark it seen); the page behind does not
 * scroll. No URL change, no analytics event.
 */
export function NoticeDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const titleId = useId();
  const boxRef = useRef<HTMLDivElement>(null);
  const okRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = onClose; }, [onClose]);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    okRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); closeRef.current(); return; }
      if (e.key !== 'Tab' || !boxRef.current) return;
      const items = Array.from(boxRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      const active = document.activeElement;
      if (e.shiftKey && (active === first || !boxRef.current.contains(active))) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && (active === last || !boxRef.current.contains(active))) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = overflow;
      if (previous && typeof previous.focus === 'function') previous.focus();
    };
  }, []);

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-3 sm:p-4"
      onMouseDown={e => { if (e.target === e.currentTarget) closeRef.current(); }}
    >
      <div
        ref={boxRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative w-full max-w-md max-h-[90vh] overflow-y-auto rounded-2xl bg-white p-5 sm:p-6 shadow-xl text-gray-900"
      >
        <button
          type="button"
          onClick={() => closeRef.current()}
          aria-label={t('beta_notice.close')}
          className={`absolute top-3 end-3 inline-flex h-9 w-9 items-center justify-center rounded-full text-gray-700 hover:bg-gray-100 ${FOCUS_RING}`}
        >
          <X size={18} aria-hidden="true" />
        </button>
        <h2 id={titleId} className="pe-10 text-xl font-bold text-[#022C22]">{t('beta_notice.title')}</h2>
        <div className="mt-3 space-y-3 text-[15px] leading-relaxed text-gray-800">
          <p>{t('beta_notice.p1')}</p>
          <p>{t('beta_notice.p2')}</p>
          <p>{t('beta_notice.p3')}</p>
        </div>
        <div className="mt-5 flex justify-center">
          <button
            ref={okRef}
            type="button"
            onClick={() => closeRef.current()}
            className={`min-h-[44px] min-w-[8rem] rounded-xl bg-emerald-700 px-6 font-semibold text-white hover:bg-emerald-800 ${FOCUS_RING}`}
          >
            {t('beta_notice.ok')}
          </button>
        </div>
      </div>
    </div>
  );
}

/** Mounted once in the site (never in the admin app). Opens on its own when shouldAutoShow allows, or from the label. */
export default function BetaNotice() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const check = () => {
      if (shouldAutoShow(window.location.hostname, window.location.pathname, undefined, isAdminHostname())) setOpen(true);
    };
    check();
    window.addEventListener(COOKIE_CHOICE_EVENT, check);
    return () => window.removeEventListener(COOKIE_CHOICE_EVENT, check);
  }, [pathname]);

  useEffect(() => {
    const show = () => setOpen(true);
    window.addEventListener(NOTICE_OPEN_EVENT, show);
    return () => window.removeEventListener(NOTICE_OPEN_EVENT, show);
  }, []);

  const close = useCallback(() => { markNoticeSeen(); setOpen(false); }, []);
  return open ? <NoticeDialog onClose={close} /> : null;
}

/** The "בהרצה" label next to the logo: a real button that reopens the notice (no storage change). */
export function BetaLabel() {
  const { t } = useTranslation();
  return (
    <button
      type="button"
      aria-label={t('beta_notice.label_aria')}
      onClick={() => window.dispatchEvent(new Event(NOTICE_OPEN_EVENT))}
      className={`inline-flex min-h-[28px] items-center rounded-full border border-amber-700 bg-amber-50 px-2.5 text-xs font-semibold text-amber-900 hover:bg-amber-100 ${FOCUS_RING}`}
    >
      {t('beta_notice.label')}
    </button>
  );
}
