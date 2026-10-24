import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { errorCode } from './api';

/** Shared bits of the admin console (SU11A-54). Touch targets are at least 44 px. */

type Tone = 'primary' | 'neutral' | 'danger';
const TONES: Record<Tone, string> = {
  primary: 'bg-emerald-700 text-white hover:bg-emerald-800 disabled:bg-emerald-400',
  neutral: 'bg-white text-gray-900 border border-gray-300 hover:bg-gray-50 disabled:text-gray-400',
  danger: 'bg-rose-700 text-white hover:bg-rose-800 disabled:bg-rose-400',
};

export function Button({ tone = 'neutral', className = '', ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { tone?: Tone }) {
  return (
    <button
      type="button"
      {...props}
      className={`min-h-[44px] px-4 rounded-xl text-sm font-semibold inline-flex items-center justify-center gap-2
        focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700
        disabled:cursor-not-allowed ${TONES[tone]} ${className}`}
    />
  );
}

export function Loading() {
  const { t } = useTranslation();
  return (
    <p className="flex items-center gap-2 text-sm text-gray-600 py-6" role="status">
      <Loader2 size={16} className="animate-spin" aria-hidden="true" /> {t('admin.common.loading')}
    </p>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  const msg = errorCode(error) === 'network' ? t('admin.common.network') : t('admin.common.error');
  return (
    <div role="alert" className="my-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">
      <p>{msg}</p>
      {onRetry && <Button className="mt-3" onClick={onRetry}>{t('admin.common.retry')}</Button>}
    </div>
  );
}

export function Card({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="bg-white rounded-2xl border border-gray-200 p-4 sm:p-5" aria-label={title}>
      <div className="flex items-center justify-between gap-2 mb-3">
        <h2 className="text-base font-bold text-gray-900">{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

/** Native <dialog>: modal focus handling and Esc come from the browser. */
export function ConfirmDialog({ open, message, tone = 'primary', busy, onConfirm, onCancel }: {
  open: boolean; message: string; tone?: Tone; busy?: boolean;
  onConfirm: () => void; onCancel: () => void;
}) {
  const { t } = useTranslation();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => { e.preventDefault(); if (!busy) onCancel(); }}
      aria-labelledby="admin-confirm-msg"
      className="rounded-2xl p-0 w-[min(92vw,26rem)] backdrop:bg-black/40"
      dir="rtl"
    >
      <div className="p-5">
        <p id="admin-confirm-msg" className="text-base text-gray-900">{message}</p>
        <div className="mt-5 flex gap-3 justify-end">
          <Button onClick={onCancel} disabled={busy}>{t('admin.common.cancel')}</Button>
          <Button tone={tone} onClick={onConfirm} disabled={busy} aria-busy={busy}>
            {busy && <Loader2 size={16} className="animate-spin" aria-hidden="true" />}
            {t('admin.common.confirm')}
          </Button>
        </div>
      </div>
    </dialog>
  );
}

export function RatingStatus({ status }: { status: string }) {
  const { t } = useTranslation();
  const tone = status === 'active' ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
    : status === 'hidden' ? 'bg-gray-100 text-gray-800 border-gray-300'
      : 'bg-amber-50 text-amber-900 border-amber-200';
  return (
    <span className={`inline-block text-xs font-semibold rounded-full border px-2 py-0.5 ${tone}`}>
      {t(`admin.rating.status_${status}`, { defaultValue: status })}
    </span>
  );
}
