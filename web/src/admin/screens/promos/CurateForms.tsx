import { useId, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { createHide, createPin, type PromoSummary } from '../../api';
import { Button, ConfirmDialog } from '../../ui';
import { INPUT, isoOrUndefined, K, writeError } from './shared';

/**
 * קידום / הסתרה forms for one promotion (SU11A-58). Each write asks for
 * confirmation first; a paid placement must be marked sponsored (the card then
 * shows ממומן), which the form says next to the toggle.
 */
function Field({ id, label, children, hint }: { id: string; label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-semibold text-gray-800 mb-1">{label}</label>
      {children}
      {hint && <p id={`${id}-hint`} className="text-xs text-gray-600 mt-1">{hint}</p>}
    </div>
  );
}

export function PinForm({ p, onDone }: { p: PromoSummary; onDone: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const id = useId();
  const [rank, setRank] = useState(1);
  const [starts, setStarts] = useState('');
  const [ends, setEnds] = useState('');
  const [sponsored, setSponsored] = useState(false);
  const [note, setNote] = useState('');
  const [asking, setAsking] = useState(false);
  const m = useMutation({
    mutationFn: () => createPin({
      chain_id: p.chain_id, promo_id: p.promo_id, rank, sponsored,
      starts_at: isoOrUndefined(starts), ends_at: isoOrUndefined(ends), note: note.trim() || undefined,
    }),
    onSuccess: () => {
      toast.success(t(`${K}.toast.pinned`));
      void qc.invalidateQueries({ queryKey: ['admin'] });
      onDone();
    },
    onError: (err) => toast.error(writeError(t, err)),
    onSettled: () => setAsking(false),
  });
  return (
    <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); setAsking(true); }}>
      <h3 className="text-sm font-bold text-gray-900">{t(`${K}.pin_form.title`)}</h3>
      <Field id={`${id}-rank`} label={t(`${K}.pin_form.rank`)}>
        <input id={`${id}-rank`} type="number" min={1} max={50} required value={rank} dir="ltr"
          onChange={e => setRank(Math.max(1, Math.min(50, Number(e.target.value) || 1)))} className={INPUT} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id={`${id}-s`} label={t(`${K}.pin_form.starts_at`)}>
          <input id={`${id}-s`} type="datetime-local" value={starts} onChange={e => setStarts(e.target.value)} className={INPUT} dir="ltr" />
        </Field>
        <Field id={`${id}-e`} label={t(`${K}.pin_form.ends_at`)}>
          <input id={`${id}-e`} type="datetime-local" value={ends} onChange={e => setEnds(e.target.value)} className={INPUT} dir="ltr" />
        </Field>
      </div>
      <div className="rounded-xl border border-amber-300 bg-amber-50 p-3">
        <label className="flex items-center gap-3 min-h-[44px] text-sm font-semibold text-gray-900">
          <input type="checkbox" checked={sponsored} onChange={e => setSponsored(e.target.checked)}
            aria-describedby={`${id}-sp`} className="w-5 h-5 accent-emerald-700" />
          {t(`${K}.pin_form.sponsored`)}
        </label>
        <p id={`${id}-sp`} className="text-xs text-amber-950 flex gap-1.5 items-start">
          <AlertTriangle size={14} className="shrink-0 mt-0.5" aria-hidden="true" /> {t(`${K}.pin_form.sponsored_warning`)}
        </p>
      </div>
      <Field id={`${id}-n`} label={t(`${K}.pin_form.note`)}>
        <input id={`${id}-n`} type="text" maxLength={200} value={note} onChange={e => setNote(e.target.value)} className={INPUT} dir="auto" />
      </Field>
      <div className="flex gap-3">
        <Button type="submit" tone="primary" disabled={m.isPending}>{t(`${K}.pin`)}</Button>
        <Button onClick={onDone} disabled={m.isPending}>{t('admin.common.cancel')}</Button>
      </div>
      <ConfirmDialog
        open={asking}
        message={t(`${K}.pin_form.${sponsored ? 'confirm_sponsored' : 'confirm'}`, { rank })}
        busy={m.isPending}
        onConfirm={() => m.mutate()}
        onCancel={() => setAsking(false)}
      />
    </form>
  );
}

export function HideForm({ p, onDone }: { p: PromoSummary; onDone: () => void }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const id = useId();
  const [reason, setReason] = useState('');
  const [ends, setEnds] = useState('');
  const [asking, setAsking] = useState(false);
  const m = useMutation({
    mutationFn: () => createHide({ chain_id: p.chain_id, promo_id: p.promo_id, reason: reason.trim(), ends_at: isoOrUndefined(ends) }),
    onSuccess: () => {
      toast.success(t(`${K}.toast.hidden`));
      void qc.invalidateQueries({ queryKey: ['admin'] });
      onDone();
    },
    onError: (err) => toast.error(writeError(t, err)),
    onSettled: () => setAsking(false),
  });
  return (
    <form className="mt-3 space-y-3" onSubmit={(e) => { e.preventDefault(); if (reason.trim()) setAsking(true); }}>
      <h3 className="text-sm font-bold text-gray-900">{t(`${K}.hide_form.title`)}</h3>
      <p className="text-xs text-gray-700">{t(`${K}.hide_form.pricing_note`)}</p>
      <Field id={`${id}-r`} label={t(`${K}.hide_form.reason`)}>
        <input id={`${id}-r`} type="text" required maxLength={200} value={reason} onChange={e => setReason(e.target.value)}
          placeholder={t(`${K}.hide_form.reason_placeholder`)} className={INPUT} dir="auto" />
      </Field>
      <Field id={`${id}-e`} label={t(`${K}.hide_form.ends_at`)}>
        <input id={`${id}-e`} type="datetime-local" value={ends} onChange={e => setEnds(e.target.value)} className={INPUT} dir="ltr" />
      </Field>
      <div className="flex gap-3">
        <Button type="submit" tone="danger" disabled={m.isPending || !reason.trim()}>{t(`${K}.hide`)}</Button>
        <Button onClick={onDone} disabled={m.isPending}>{t('admin.common.cancel')}</Button>
      </div>
      <ConfirmDialog
        open={asking}
        message={t(`${K}.hide_form.confirm`)}
        tone="danger"
        busy={m.isPending}
        onConfirm={() => m.mutate()}
        onCancel={() => setAsking(false)}
      />
    </form>
  );
}
