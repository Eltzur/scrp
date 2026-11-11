import { useId, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getI18n, useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';
import {
  getAnnouncements, saveAnnouncement, setAnnouncementActive, type Announcement,
} from '../api';
import { fmtDate } from '../format';
import { Button, Card, ErrorBox, Loading } from '../ui';
import he from '../i18n/notices.he.json';
import en from '../i18n/notices.en.json';

/**
 * SU11A-77: "הודעות לאפליקציה" - the notice the app shows once per device
 * (from 1.2.4, SU11B-8). One card per scope (iPhone / Android / both). The
 * server validates every save; this screen only shows the rules and the errors.
 */
const i18n = getI18n();
i18n.addResourceBundle('he', 'translation', { admin: { notices: he } }, true, false);
i18n.addResourceBundle('en', 'translation', { admin: { notices: en } }, true, false);
const K = 'admin.notices';
const FOCUS = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700';

type ErrBody = { code?: string; field?: string; word?: string };

function errorText(t: (k: string, o?: Record<string, unknown>) => string, err: unknown): string {
  const d = (err as AxiosError<ErrBody>)?.response?.data ?? {};
  const key = {
    empty: 'err_empty', too_long: 'err_too_long', markup_not_allowed: 'err_markup',
    links_not_allowed: 'err_links', beta_wording_not_allowed_ios: 'err_beta',
  }[d.code ?? ''] ?? 'err_other';
  const field = d.field === 'title' || d.field === 'body' ? ` (${t(`${K}.field_${d.field}`)})` : '';
  return t(`${K}.${key}`, { word: d.word ?? '' }) + field;
}

function NoticeCard({ a, max }: { a: Announcement; max: { title: number; body: number } }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const id = useId();
  const [title, setTitle] = useState(a.title);
  const [body, setBody] = useState(a.body);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const dirty = title !== a.title || body !== a.body;

  const run = async (fn: () => Promise<Announcement>, ok: (r: Announcement) => string) => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await fn();
      setMsg({ ok: true, text: ok(r) });
      await qc.invalidateQueries({ queryKey: ['admin-announcements'] });
    } catch (err) {
      setMsg({ ok: false, text: errorText(t, err) });
    } finally {
      setBusy(false);
    }
  };

  const scope = t(`${K}.scope_${a.platform}`);
  return (
    <Card title={scope}>
      {a.platform === 'both' && <p className="text-xs text-gray-700 -mt-2 mb-3">{t(`${K}.scope_both_note`)}</p>}
      <div className="flex items-center justify-between gap-3 mb-3">
        <span id={`${id}-sw`} className="text-sm font-medium text-gray-900">{t(`${K}.switch_label`)}</span>
        <span className="flex items-center gap-2">
          <span className="text-sm font-semibold text-gray-900">{t(a.active ? `${K}.active` : `${K}.inactive`)}</span>
          <button
            type="button" role="switch" aria-checked={a.active} aria-labelledby={`${id}-sw`} disabled={busy || dirty}
            onClick={() => run(() => setAnnouncementActive(a.platform, !a.active), r => t(r.active ? `${K}.active` : `${K}.inactive`))}
            className={`relative inline-flex items-center h-8 w-14 shrink-0 rounded-full border-2 transition-colors ${FOCUS}
              disabled:opacity-50 ${a.active ? 'bg-emerald-700 border-emerald-700' : 'bg-gray-200 border-gray-500'}`}
          >
            <span aria-hidden="true"
              className={`inline-block h-6 w-6 rounded-full bg-white shadow transition-transform ${a.active ? '-translate-x-6' : 'translate-x-0'}`} />
          </button>
        </span>
      </div>

      <label htmlFor={`${id}-t`} className="block text-sm font-medium text-gray-900">{t(`${K}.title_label`)}</label>
      <input
        id={`${id}-t`} value={title} maxLength={max.title} onChange={e => setTitle(e.target.value)} dir="auto"
        aria-describedby={`${id}-tc`}
        className={`mt-1 w-full min-h-[44px] rounded-lg border border-gray-500 bg-white px-3 text-sm text-gray-900 ${FOCUS}`}
      />
      <p id={`${id}-tc`} className="mt-0.5 text-xs text-gray-700 text-end tabular-nums" dir="ltr">
        {t(`${K}.counter`, { n: title.trim().length, max: max.title })}
      </p>

      <label htmlFor={`${id}-b`} className="block text-sm font-medium text-gray-900 mt-2">{t(`${K}.body_label`)}</label>
      <textarea
        id={`${id}-b`} value={body} maxLength={max.body} rows={5} onChange={e => setBody(e.target.value)} dir="auto"
        aria-describedby={`${id}-bc ${id}-rules`}
        className={`mt-1 w-full rounded-lg border border-gray-500 bg-white px-3 py-2 text-sm text-gray-900 ${FOCUS}`}
      />
      <p id={`${id}-bc`} className="mt-0.5 text-xs text-gray-700 text-end tabular-nums" dir="ltr">
        {t(`${K}.counter`, { n: body.trim().length, max: max.body })}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button tone="primary" disabled={busy || !dirty}
          onClick={() => run(() => saveAnnouncement(a.platform, { title, body }), r => t(`${K}.saved`, { v: r.version }))}>
          {busy ? t(`${K}.saving`) : t(`${K}.save`)}
        </Button>
        <span className="text-xs text-gray-700" dir="auto">
          {t(`${K}.version`, { v: a.version, at: fmtDate(a.updated_at) })}
        </span>
      </div>
      {msg && (
        <p role={msg.ok ? 'status' : 'alert'} className={`mt-2 text-sm ${msg.ok ? 'text-emerald-800' : 'text-rose-800'}`}>{msg.text}</p>
      )}

      <div className="mt-4">
        <p className="text-xs font-semibold text-gray-800 mb-1">{t(`${K}.preview`)}</p>
        <div className="rounded-xl border border-gray-300 bg-gray-50 p-3" aria-live="polite">
          {title.trim() || body.trim() ? (
            <>
              <p className="font-bold text-gray-900" dir="auto">{title.trim()}</p>
              <p className="mt-1 text-sm text-gray-800 whitespace-pre-line" dir="auto">{body.trim()}</p>
            </>
          ) : <p className="text-sm text-gray-700">{t(`${K}.preview_empty`)}</p>}
        </div>
      </div>

      <div id={`${id}-rules`} className="mt-3 text-xs text-gray-700 space-y-1">
        <p className="font-semibold text-gray-800">{t(`${K}.rules_title`)}</p>
        <p>{t(`${K}.rule_plain`)}</p>
        <p>{t(`${K}.rule_payment`)}</p>
        {a.platform !== 'android' && <p>{t(`${K}.rule_ios`)}</p>}
        <p>{t(`${K}.rule_version`)}</p>
      </div>
    </Card>
  );
}

export default function NoticesScreen() {
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ['admin-announcements'], queryFn: getAnnouncements, refetchOnWindowFocus: false });
  if (q.isLoading) return <Loading />;
  if (q.isError || !q.data) return <ErrorBox error={q.error} onRetry={() => q.refetch()} />;
  const max = { title: q.data.rules.title_max, body: q.data.rules.body_max };
  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-800">{t(`${K}.intro`)}</p>
      {q.data.items.map(a => (
        <NoticeCard key={`${a.platform}-${a.version}-${a.active}`} a={a} max={max} />
      ))}
    </div>
  );
}
