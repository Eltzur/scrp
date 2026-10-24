/** Formatting for the admin console (SU11A-54). Times are shown in Israel time. */
const TZ = 'Asia/Jerusalem';
const dtFmt = new Intl.DateTimeFormat('he-IL', { timeZone: TZ, dateStyle: 'short', timeStyle: 'short' });
const dayKey = new Intl.DateTimeFormat('en-CA', { timeZone: TZ });

/** Postgres to_char(..., 'OF') writes "+03"; Date() needs "+03:00". */
export function parseTs(iso: string): Date {
  return new Date(/[+-]\d\d$/.test(iso) ? `${iso}:00` : iso);
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = parseTs(iso);
  return Number.isNaN(d.getTime()) ? iso : dtFmt.format(d);
}

/** Israel-time day of a timestamp: today / yesterday / older (or never). */
export function freshness(iso: string | null, now = new Date()): 'today' | 'yesterday' | 'older' | 'never' {
  if (!iso) return 'never';
  const d = parseTs(iso);
  if (Number.isNaN(d.getTime())) return 'never';
  const k = dayKey.format(d);
  if (k === dayKey.format(now)) return 'today';
  if (k === dayKey.format(new Date(now.getTime() - 86_400_000))) return 'yesterday';
  return 'older';
}

export function fmtBytes(n: number | null | undefined): string | null {
  if (n == null) return null;
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let v = n;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(i >= 3 ? 1 : 0)} ${units[i]}`;
}

/** "rating.ban_author" -> the admin.audit.actions.rating_ban_author label. */
export function actionLabel(t: (k: string, o?: Record<string, unknown>) => string, action: string): string {
  return t(`admin.audit.actions.${action.replace('.', '_')}`, { defaultValue: action });
}
