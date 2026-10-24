import axios, { AxiosError } from 'axios';
import { supabase } from '../lib/supabase';

/**
 * Admin console API client (SU11A-54). Every call goes to api-super with the
 * session's access token; the API checks admin allowlist + aal2 on each one.
 * Nothing here talks to the database or to any other service.
 */
const http = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 20000,
});

http.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession();
  if (session?.access_token) config.headers.Authorization = `Bearer ${session.access_token}`;
  return config;
});

/** "admin_required" | "mfa_required" | "rate_limited" | "network" | "http_<status>" */
export function errorCode(err: unknown): string {
  const e = err as AxiosError<{ code?: string }>;
  if (!e?.response) return 'network';
  return e.response.data?.code ?? `http_${e.response.status}`;
}

export interface Report { id: number; source: string; reason: string | null; created_at: string }

export interface QueueItem {
  id: number;
  item_code: string;
  item_name: string | null;
  rating: number;
  comment: string | null;
  status: string;
  created_at: string;
  updated_at: string;
  reviewed_at: string | null;
  reports: Report[];
  report_count: number;
  latest_report_at: string | null;
  report_sources: string[];
  report_reasons: string[];
}

export interface RatingDetail extends Omit<QueueItem, 'report_count' | 'latest_report_at' | 'report_sources' | 'report_reasons'> {
  author: { banned: boolean | null; active_ratings: number | null };
  audit: { id: number; at: string; action: string }[];
}

export interface HistoryItem {
  id: number; item_code: string; item_name: string | null; rating: number;
  comment: string | null; status: string; reviewed_at: string; last_action: string | null;
}

export interface AuditItem {
  id: number; at: string; actor: string; action: string;
  target_type: string | null; target_id: string | null; detail: Record<string, unknown> | null;
}

export interface ChainStatus {
  chain_name: string; last_loaded_at: string | null;
  stores_loaded_72h: number | null; stores_configured: number | null;
}

export interface BuildStamp { built_at: string | null; rows_approx: number | null }

export interface Status {
  generated_at: string;
  cache_age_s: number;
  chains: ChainStatus[] | null;
  search_items: BuildStamp | null;
  search_item_prices: BuildStamp | null;
  moderation: { pending: number; hidden_7d: number; banned_users: number } | null;
  db_size_bytes: number | null;
  disk: { path: string; total_bytes: number; free_bytes: number } | null;
  memory: { process_rss_bytes: number | null; system_total_bytes: number | null; system_available_bytes: number | null };
  process: { pid: number };
  counters: {
    scope: string; pid: number; since: string; window_hours: number;
    requests: number; http_5xx: number; query_timeout: number; http_429: number;
  };
}

export const getMe = () => http.get<{ is_admin: boolean; mfa: boolean }>('/admin/me').then(r => r.data);
export const getStatus = () => http.get<Status>('/admin/status').then(r => r.data);
export const getQueue = () =>
  http.get<{ count: number; items: QueueItem[] }>('/admin/ratings/pending').then(r => r.data);
export const getRating = (id: number) => http.get<RatingDetail>(`/admin/ratings/${id}`).then(r => r.data);
export const moderate = (id: number, action: 'hide' | 'keep' | 'restore') =>
  http.post<{ ok: boolean; status: string }>(`/admin/ratings/${id}/moderate`, { action }).then(r => r.data);
export const banAuthor = (id: number, ban: boolean) =>
  http.post<{ ok: boolean; banned: boolean; ratings_hidden: number }>(`/admin/ratings/${id}/ban-author`, { ban })
    .then(r => r.data);

export interface Cursor { before: string; before_id: number }
export const getHistory = (cursor?: Cursor | null) =>
  http.get<{ items: HistoryItem[]; next: Cursor | null }>('/admin/ratings/history',
    { params: { limit: 50, ...(cursor ?? {}) } }).then(r => r.data);
export const getAudit = (before?: number | null) =>
  http.get<{ items: AuditItem[]; next_before: number | null }>('/admin/audit',
    { params: { limit: 50, ...(before ? { before } : {}) } }).then(r => r.data);
