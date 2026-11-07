import type { StatsBody, StatsRun, StatsSeries, StatsSource } from '../../api';

/**
 * Pure helpers of the סטטיסטיקות screen (SU11A-69): range days, totals per
 * dimension, daily totals (a day the job has not stored is null, never 0), the
 * card state, and the SVG polyline of a series. No React here, so
 * scripts/admin-stats.test.mjs can run them in node.
 */
export const RANGES = [7, 30, 90] as const;
export type Range = typeof RANGES[number];

export const WEB_HOSTS = ['super.xxl.co.il', 'xxl.co.il', 'www.xxl.co.il', 'fly.xxl.co.il'] as const;
/** SU11A-70: 'admin' = the admin console (its Referer), its own row, never in the dashboard total. */
export const PLATFORMS = ['web', 'android', 'ios', 'admin', 'other', 'bot'] as const;

/** Every day from..to (YYYY-MM-DD, inclusive). */
export function dayList(from: string, to: string): string[] {
  const out: string[] = [];
  const d = new Date(`${from}T00:00:00Z`);
  const end = new Date(`${to}T00:00:00Z`);
  while (d <= end && out.length < 500) {
    out.push(d.toISOString().slice(0, 10));
    d.setUTCDate(d.getUTCDate() + 1);
  }
  return out;
}

export function pick(series: StatsSeries[], source: StatsSource, metric: string): StatsSeries[] {
  return series.filter(s => s.source === source && s.metric === metric);
}

/** Sum over the range, per dimension. */
export function totals(series: StatsSeries[], source: StatsSource, metric: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const s of pick(series, source, metric)) {
    out[s.dimension] = (out[s.dimension] ?? 0) + s.points.reduce((a, [, v]) => a + v, 0);
  }
  return out;
}

export function total(series: StatsSeries[], source: StatsSource, metric: string, dims?: readonly string[]): number {
  const t = totals(series, source, metric);
  return Object.entries(t).filter(([d]) => !dims || dims.includes(d)).reduce((a, [, v]) => a + v, 0);
}

/** The latest stored value (e.g. active devices), or null. */
export function latest(series: StatsSeries[], source: StatsSource, metric: string): number | null {
  let best: [string, number] | null = null;
  for (const s of pick(series, source, metric)) {
    for (const p of s.points) if (!best || p[0] > best[0]) best = p;
  }
  return best ? best[1] : null;
}

/** Daily sum over the chosen dimensions; null where nothing is stored that day. */
export function daily(series: StatsSeries[], source: StatsSource, metric: string, days: string[],
  dims?: readonly string[]): (number | null)[] {
  const byDay = new Map<string, number>();
  for (const s of pick(series, source, metric)) {
    if (dims && !dims.includes(s.dimension)) continue;
    for (const [d, v] of s.points) byDay.set(d, (byDay.get(d) ?? 0) + v);
  }
  return days.map(d => (byDay.has(d) ? byDay.get(d)! : null));
}

export type CardState = 'ok' | 'error' | 'not_connected' | 'never_run' | 'unavailable';

export function cardState(body: StatsBody | undefined, source: StatsSource): CardState {
  if (!body || body.unavailable) return 'unavailable';
  const run: StatsRun | undefined = body.sources[source];
  if (!run || run.status === 'never_run') return 'never_run';
  if (run.status === 'not_configured') return 'not_connected';
  return run.status;
}

/** Share in percent (one decimal), or null when the whole is 0. */
export function share(part: number, whole: number): number | null {
  return whole > 0 ? Math.round((part / whole) * 1000) / 10 : null;
}

/** "super.xxl.co.il/categories/D02" -> [host, path]; "host|domain" -> [host, domain]. */
export function splitDim(dim: string, sep: '/' | '|'): [string, string] {
  const i = dim.indexOf(sep);
  if (i < 0) return [dim, ''];
  return [dim.slice(0, i), sep === '/' ? dim.slice(i) : dim.slice(i + 1)];
}

/** SVG polyline segments (a null day breaks the line) in a w x h box. */
export function linePaths(values: (number | null)[], max: number, w: number, h: number, pad = 4): string[] {
  const n = values.length;
  const x = (i: number) => (n <= 1 ? w / 2 : pad + (i * (w - 2 * pad)) / (n - 1));
  const y = (v: number) => h - pad - (max > 0 ? (v / max) * (h - 2 * pad) : 0);
  const out: string[] = [];
  let cur: string[] = [];
  values.forEach((v, i) => {
    if (v == null) {
      if (cur.length) out.push(cur.join(' '));
      cur = [];
      return;
    }
    cur.push(`${x(i).toFixed(1)},${y(v).toFixed(1)}`);
  });
  if (cur.length) out.push(cur.join(' '));
  return out;
}

/** Day label "05.11" for a YYYY-MM-DD day. */
export const shortDay = (d: string) => `${d.slice(8, 10)}.${d.slice(5, 7)}`;
