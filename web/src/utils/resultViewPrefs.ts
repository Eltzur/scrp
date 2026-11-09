/**
 * SU11A-72: result view modes (grid / list / comparison table) - the part the
 * main chunk needs: the view / page-size / chain-choice preferences and the
 * table's page-size clamp. The list / table logic is in resultViews.ts (lazy).
 *
 * Persistence is localStorage only (keys xxl_*), never the account and never
 * the URL, so a view or page-size change is not a navigation and GA4 sees
 * nothing (SU11A-71: one page_view per route).
 */

export type ViewMode = 'grid' | 'list' | 'table';
export const VIEW_MODES: ViewMode[] = ['grid', 'list', 'table'];

/** 0 = "הכל": everything one request returns (the endpoint's own cap). */
export type PageSize = 10 | 25 | 50 | 100 | 0;
export const LIST_PAGE_SIZES: PageSize[] = [10, 25, 50, 100, 0];
export const TABLE_PAGE_SIZES: PageSize[] = [10, 25, 50];
export const DEFAULT_PAGE_SIZE: PageSize = 25;
export const TABLE_DEFAULT_COLUMNS = 5;
export const TABLE_MAX_COLUMNS = 8;

export const STORAGE_KEYS = {
  view: 'xxl_result_view',
  pageSize: 'xxl_result_page_size',
  chains: 'xxl_table_chains',
} as const;

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

function storage(): StorageLike | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;            // access itself can throw (blocked storage)
  }
}

function read(key: string, s: StorageLike | null = storage()): string | null {
  try { return s ? s.getItem(key) : null; } catch { return null; }
}

function write(key: string, value: string, s: StorageLike | null = storage()): void {
  try { s?.setItem(key, value); } catch { /* private mode / quota: not remembered, still works */ }
}

export function loadView(s?: StorageLike | null): ViewMode {
  const v = read(STORAGE_KEYS.view, s === undefined ? storage() : s);
  return (VIEW_MODES as string[]).includes(v ?? '') ? (v as ViewMode) : 'grid';
}

export function saveView(v: ViewMode, s?: StorageLike | null): void {
  write(STORAGE_KEYS.view, v, s === undefined ? storage() : s);
}

export function loadPageSize(s?: StorageLike | null): PageSize {
  const raw = read(STORAGE_KEYS.pageSize, s === undefined ? storage() : s);
  const n = raw === null || raw.trim() === '' ? NaN : Number(raw);
  return (LIST_PAGE_SIZES as number[]).includes(n) ? (n as PageSize) : DEFAULT_PAGE_SIZE;
}

export function savePageSize(n: PageSize, s?: StorageLike | null): void {
  write(STORAGE_KEYS.pageSize, String(n), s === undefined ? storage() : s);
}

const CHAIN_ID = /^\d{13}$/;

export function loadChains(s?: StorageLike | null): string[] {
  try {
    const raw = JSON.parse(read(STORAGE_KEYS.chains, s === undefined ? storage() : s) ?? '[]');
    if (!Array.isArray(raw)) return [];
    return [...new Set(raw.filter((x): x is string => typeof x === 'string' && CHAIN_ID.test(x)))].slice(0, TABLE_MAX_COLUMNS);
  } catch {
    return [];
  }
}

export function saveChains(ids: string[], s?: StorageLike | null): void {
  write(STORAGE_KEYS.chains, JSON.stringify(ids.slice(0, TABLE_MAX_COLUMNS)), s === undefined ? storage() : s);
}

/** The page size the view actually uses, and whether it was clamped (table: 10 / 25 / 50 only). */
export function effectivePageSize(view: ViewMode, size: PageSize): { size: PageSize; clamped: boolean } {
  if (view === 'table' && !(TABLE_PAGE_SIZES as number[]).includes(size)) return { size: 50, clamped: true };
  return { size, clamped: false };
}

