import { useId, useState, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { getI18n, useTranslation } from 'react-i18next';
import { getStats, type StatsBody, type StatsSource } from '../api';
import { fmtDate } from '../format';
import { Button, COL_NUM, COL_TEXT, Card, ErrorBox, Loading } from '../ui';
import he from '../i18n/stats.he.json';
import en from '../i18n/stats.en.json';
import LineChart from './stats/LineChart';
import { readInternal, writeInternal } from './stats/internalCookie';
import {
  cardState, daily, dayList, latest, PLATFORMS, RANGES, share, splitDim, total, totals, WEB_HOSTS,
  type CardState, type Range,
} from './stats/statsView';

/**
 * סטטיסטיקות (SU11A-69): website traffic (nginx logs next to GA4), app activity
 * per platform (API requests), Google Play installs and App Store downloads /
 * impressions, each with its "updated to" day. Read-only; everything is a daily
 * aggregate from GET /admin/stats (scripts/stats_collect.py fills it at 03:30).
 * GA4 / Play / App Store show "לא מחובר" with a hint until Dude connects them.
 * Its strings ship with this lazy chunk (admin/i18n/stats.*.json).
 */
const i18n = getI18n();
i18n.addResourceBundle('he', 'translation', { admin: { stats: he } }, true, false);
i18n.addResourceBundle('en', 'translation', { admin: { stats: en } }, true, false);

const K = 'admin.stats';
const n = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString('he-IL'));
const pct = (v: number | null) => (v == null ? '—' : `${v}%`);

const CHIP: Record<CardState, string> = {
  ok: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  error: 'bg-rose-50 text-rose-800 border-rose-200',
  not_connected: 'bg-gray-100 text-gray-800 border-gray-300',
  never_run: 'bg-amber-50 text-amber-900 border-amber-200',
  unavailable: 'bg-gray-100 text-gray-800 border-gray-300',
};

/** The state chip, "updated to", and the hint / error / note line of one source. */
export function SourceStatus({ body, source }: { body: StatsBody; source: StatsSource }) {
  const { t } = useTranslation();
  const st = cardState(body, source);
  const run = body.sources?.[source];
  const note = run?.note ?? '';
  const notes: string[] = [];
  if (note.includes('$host')) notes.push(t(`${K}.notes.no_host`));
  if (note.includes('partial')) notes.push(t(`${K}.notes.partial`));
  if (note.includes('analytics_request_missing')) notes.push(t(`${K}.notes.analytics_request_missing`));
  return (
    <div className="text-xs text-gray-700 space-y-1 mb-2">
      <p className="flex flex-wrap items-center gap-2">
        <span className={`inline-block font-semibold rounded-full border px-2 py-0.5 ${CHIP[st]}`}>
          {t(`${K}.state.${st}`)}
        </span>
        {run?.as_of && <span>{t(`${K}.updated_as_of`, { day: run.as_of })}</span>}
      </p>
      {st === 'not_connected' && (source === 'ga4' || source === 'play' || source === 'appstore') && (
        <p>{t(`${K}.hints.${source}`)}</p>
      )}
      {st === 'never_run' && <p>{t(`${K}.never_run_hint`)}</p>}
      {st === 'unavailable' && <p>{t(`${K}.unavailable_hint`)}</p>}
      {st === 'error' && run?.error && (
        <p className="text-rose-800">
          {t(`${K}.last_error`, { error: run.error })}
          {run.last_error_at && <span className="text-gray-600"> ({fmtDate(run.last_error_at)})</span>}
        </p>
      )}
      {notes.map(x => <p key={x}>{x}</p>)}
    </div>
  );
}

function Table({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto -mx-1">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-gray-600 border-b border-gray-200">
            {head.map((h, j) => <th key={h} scope="col" className={`py-2 px-1 font-medium ${j === 0 ? COL_TEXT : COL_NUM}`}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-gray-100 last:border-0">
              {r.map((c, j) => j === 0
                ? <th key={j} scope="row" className={`py-2 px-1 font-medium text-gray-900 ${COL_TEXT}`}>{c}</th>
                : <td key={j} className={`py-2 px-1 ${COL_NUM}`}><span dir="ltr">{c}</span></td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-gray-50 border border-gray-200 px-3 py-2">
      <dt className="text-xs text-gray-600">{label}</dt>
      <dd className="text-lg font-bold text-gray-900 tabular-nums" dir="ltr">{value}</dd>
    </div>
  );
}

function WebCard({ b, days }: { b: StatsBody; days: string[] }) {
  const { t } = useTranslation();
  const s = b.series;
  const pv = totals(s, 'web', 'page_views');
  const vis = totals(s, 'web', 'visitors');
  const bots = totals(s, 'web', 'bot_page_views');
  const rejected = totals(s, 'web', 'rejected_requests');
  const internal = totals(s, 'web', 'internal_page_views');
  const gaUsers = totals(s, 'ga4', 'users');
  const gaPv = totals(s, 'ga4', 'page_views');
  const ga = cardState(b, 'ga4') === 'ok' || Object.keys(gaPv).length > 0;
  const hosts = [...WEB_HOSTS, ...(pv['(unknown)'] != null ? ['(unknown)'] : [])];
  const hostLabel = (h: string) => (h === '(unknown)' ? t(`${K}.web.unknown_host`) : h);
  const row = (h: string | null) => {
    const p = h == null ? total(s, 'web', 'page_views') : (pv[h] ?? 0);
    const bt = h == null ? total(s, 'web', 'bot_page_views') : (bots[h] ?? 0);
    return [
      h == null ? t(`${K}.web.total`) : hostLabel(h),
      n(p),
      n(h == null ? total(s, 'web', 'visitors') : (vis[h] ?? 0)),
      pct(share(bt, p + bt)),
      n(h == null ? total(s, 'web', 'rejected_requests') : (rejected[h] ?? 0)),
      n(h == null ? total(s, 'web', 'internal_page_views') : (internal[h] ?? 0)),
      ...(ga ? [n(h == null ? total(s, 'ga4', 'users') : gaUsers[h] ?? 0),
        n(h == null ? total(s, 'ga4', 'page_views') : gaPv[h] ?? 0)] : []),
    ];
  };
  const pathLabel = (p: string) => (p === '/(other)' ? t(`${K}.web.other_route`) : p);
  const refLabel = (r: string) => (r === '(direct)' ? t(`${K}.web.direct`) : r === '(ip)' ? t(`${K}.web.ip_ref`) : r);
  return (
    <Card title={t(`${K}.web.title`)}>
      <SourceStatus body={b} source="web" />
      <h3 className="text-sm font-semibold text-gray-800 mt-1">GA4</h3>
      <SourceStatus body={b} source="ga4" />
      <Table
        head={[t(`${K}.web.host`), t(`${K}.web.page_views`), t(`${K}.web.visitors`), t(`${K}.web.bots`),
          t(`${K}.web.rejected`), t(`${K}.web.internal`),
          ...(ga ? [t(`${K}.web.ga4_users`), t(`${K}.web.ga4_page_views`)] : [])]}
        rows={[...hosts.map(h => row(h)), row(null)]}
      />
      <p className="text-xs text-gray-600 mt-1">{t(`${K}.web.counting_note`)}</p>
      <LineChart title={t(`${K}.web.chart`)} days={days} lines={[
        { label: t(`${K}.web.series_nginx`), values: daily(s, 'web', 'page_views', days) },
        ...(ga ? [{ label: t(`${K}.web.series_ga4`), values: daily(s, 'ga4', 'page_views', days) }] : []),
      ]} />
      <details className="mt-3 text-sm text-gray-700">
        <summary className="cursor-pointer min-h-[44px] inline-flex items-center font-semibold text-emerald-800
          underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700 rounded">
          {t(`${K}.web.why_title`)}
        </summary>
        <p className="mt-1">{t(`${K}.web.why`)}</p>
      </details>
      <p className="text-xs text-gray-600 mt-1">{t(`${K}.web.ga4_note`)}</p>
      <div className="grid gap-4 md:grid-cols-2 mt-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-800 mb-1">{t(`${K}.web.top_paths`)}</h3>
          {b.top_paths.length === 0 ? <p className="text-sm text-gray-500">{t(`${K}.no_data`)}</p> : (
            <Table head={[t(`${K}.web.page`), t(`${K}.web.views`)]}
              rows={b.top_paths.map(p => {
                const [host, path] = splitDim(p.dimension, '/');
                return [<span key="p"><bdi dir="ltr">{pathLabel(path)}</bdi> <span className="text-xs text-gray-500">{host}</span></span>, n(p.value)];
              })} />
          )}
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-800 mb-1">{t(`${K}.web.top_referrers`)}</h3>
          {b.top_referrers.length === 0 ? <p className="text-sm text-gray-500">{t(`${K}.no_data`)}</p> : (
            <Table head={[t(`${K}.web.top_referrers`), t(`${K}.web.views`)]}
              rows={b.top_referrers.map(r => {
                const [host, ref] = splitDim(r.dimension, '|');
                return [<span key="r"><bdi dir="ltr">{refLabel(ref)}</bdi> <span className="text-xs text-gray-500">{host}</span></span>, n(r.value)];
              })} />
          )}
        </div>
      </div>
    </Card>
  );
}

function ApiCard({ b, days }: { b: StatsBody; days: string[] }) {
  const { t } = useTranslation();
  const s = b.series;
  const calls = totals(s, 'api', 'calls');
  const errs = totals(s, 'api', 'errors_5xx');
  const all = total(s, 'api', 'calls');
  const human = (p: string) => t(`${K}.api.platforms.${p}`);
  return (
    <Card title={t(`${K}.api.title`)}>
      <SourceStatus body={b} source="api" />
      <Table head={[t(`${K}.api.platform`), t(`${K}.api.calls`), t(`${K}.api.share`), t(`${K}.api.errors`)]}
        rows={PLATFORMS.map(p => [human(p), n(calls[p] ?? 0), pct(share(calls[p] ?? 0, all)), n(errs[p] ?? 0)])} />
      <LineChart title={t(`${K}.api.chart`)} days={days}
        lines={(['android', 'ios', 'web'] as const).map(p => ({ label: human(p), values: daily(s, 'api', 'calls', days, [p]) }))} />
      <p className="text-xs text-gray-600 mt-2">{t(`${K}.api.note`)}</p>
    </Card>
  );
}

function PlayCard({ b, days }: { b: StatsBody; days: string[] }) {
  const { t } = useTranslation();
  const s = b.series;
  return (
    <Card title={t(`${K}.play.title`)}>
      <SourceStatus body={b} source="play" />
      <dl className="grid grid-cols-3 gap-2">
        <Stat label={t(`${K}.play.installs`)} value={n(total(s, 'play', 'installs'))} />
        <Stat label={t(`${K}.play.uninstalls`)} value={n(total(s, 'play', 'uninstalls'))} />
        <Stat label={t(`${K}.play.active_devices`)} value={n(latest(s, 'play', 'active_devices'))} />
      </dl>
      <LineChart title={t(`${K}.play.chart`)} days={days}
        lines={[{ label: t(`${K}.play.installs`), values: daily(s, 'play', 'installs', days) },
          { label: t(`${K}.play.uninstalls`), values: daily(s, 'play', 'uninstalls', days) }]} />
      <p className="text-xs text-gray-600 mt-2">{t(`${K}.play.note`)}</p>
    </Card>
  );
}

function AppStoreCard({ b, days }: { b: StatsBody; days: string[] }) {
  const { t } = useTranslation();
  const s = b.series;
  return (
    <Card title={t(`${K}.appstore.title`)}>
      <SourceStatus body={b} source="appstore" />
      <dl className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {(['downloads', 'redownloads', 'updates', 'impressions', 'page_views'] as const).map(m => (
          <Stat key={m} label={t(`${K}.appstore.${m}`)} value={n(total(s, 'appstore', m))} />
        ))}
      </dl>
      <LineChart title={t(`${K}.appstore.chart`)} days={days}
        lines={[{ label: t(`${K}.appstore.downloads`), values: daily(s, 'appstore', 'downloads', days) }]} />
      <p className="text-xs text-gray-600 mt-2">{t(`${K}.appstore.note`)}</p>
    </Card>
  );
}

/** SU11A-70: "don't count this browser" (cookie xxl_internal, per browser / phone). */
export function InternalSwitch() {
  const { t } = useTranslation();
  const id = useId();
  const [on, setOn] = useState<boolean>(readInternal);
  const [refused, setRefused] = useState(false);
  const toggle = () => {
    const want = !on;
    const got = writeInternal(want);
    setOn(got);
    setRefused(got !== want);
  };
  return (
    <section aria-labelledby={`${id}-l`} className="bg-white rounded-2xl border border-gray-200 p-4 sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 id={`${id}-l`} className="text-base font-bold text-gray-900">{t(`${K}.internal.title`)}</h2>
        <button type="button" role="switch" aria-checked={on} aria-labelledby={`${id}-l`} aria-describedby={`${id}-d`}
          onClick={toggle}
          className={`relative inline-flex items-center h-8 w-14 shrink-0 rounded-full border-2 transition-colors
            focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700
            ${on ? 'bg-emerald-700 border-emerald-700' : 'bg-gray-200 border-gray-400'}`}>
          <span aria-hidden="true"
            className={`inline-block h-6 w-6 rounded-full bg-white shadow transition-transform ${on ? '-translate-x-6' : 'translate-x-0'}`} />
        </button>
      </div>
      <p className="text-sm font-semibold mt-1 text-gray-900">{t(on ? `${K}.internal.on` : `${K}.internal.off`)}</p>
      <div id={`${id}-d`} className="text-xs text-gray-700 mt-1 space-y-1">
        <p>{t(`${K}.internal.explain`)}</p>
        <p>{t(`${K}.internal.api_note`)}</p>
      </div>
      {refused && <p role="status" className="text-xs text-rose-800 mt-1">{t(`${K}.internal.refused`)}</p>}
    </section>
  );
}

export function StatsView({ b }: { b: StatsBody }) {
  const days = dayList(b.from, b.to);
  return (
    <div className="space-y-4">
      <WebCard b={b} days={days} />
      <ApiCard b={b} days={days} />
      <div className="grid gap-4 md:grid-cols-2">
        <PlayCard b={b} days={days} />
        <AppStoreCard b={b} days={days} />
      </div>
    </div>
  );
}

export default function StatsScreen() {
  const { t } = useTranslation();
  const [range, setRange] = useState<Range>(30);
  const q = useQuery({ queryKey: ['admin', 'stats', range], queryFn: () => getStats(range), retry: 0,
    staleTime: 5 * 60_000 });

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-700">{t(`${K}.intro`)}</p>
      <InternalSwitch />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div role="group" aria-label={t(`${K}.range`)} className="flex gap-1">
          {RANGES.map(r => (
            <Button key={r} onClick={() => setRange(r)} aria-pressed={range === r}
              tone={range === r ? 'primary' : 'neutral'}>
              {t(`${K}.range_days`, { n: r })}
            </Button>
          ))}
        </div>
        <Button onClick={() => void q.refetch()} disabled={q.isFetching} aria-label={t(`${K}.refresh`)}>
          <RefreshCw size={16} className={q.isFetching ? 'animate-spin' : ''} aria-hidden="true" />
          {t(`${K}.refresh`)}
        </Button>
      </div>
      {q.isPending ? <Loading /> : q.isError
        ? <ErrorBox error={q.error} onRetry={() => void q.refetch()} />
        : <StatsView b={q.data} />}
    </div>
  );
}
