/**
 * SU11A-67: the category browse API (/categories/browse-tree, /categories/{id}/items).
 * Imported only by the lazy categories page, so none of it is in the main chunk.
 */
import { http } from './client';
import type { ProductWithPrices } from './client';

export interface BrowseNode {
  id: string;
  level: number;
  name_he: string;
  name_en: string;
  /** Visible live items under the node (this build). */
  count: number;
  /** Categories / sub-categories only: >= min_linked items. */
  linked?: boolean;
  /** Linked sub-nodes only. */
  children: BrowseNode[];
}

export interface BrowseTree {
  min_linked: number;
  total: number;
  built_at: string | null;
  departments: BrowseNode[];
}

export interface CategoryRef { id: string; level: number; name_he: string; name_en: string }

export interface CategoryItemsResult {
  category: CategoryRef;
  path: CategoryRef[];
  children: (CategoryRef & { count: number })[];
  count: number;
  total: number;
  total_exact: boolean;
  has_more: boolean;
  sort: string;
  /** SU11A-68: the search text used (null = none, or under 2 characters). */
  q?: string | null;
  corrected_from?: string | null;
  items: (ProductWithPrices & { category_id: string | null })[];
}

export interface CategoryItemsParams {
  city?: string;
  chain?: string;
  sort?: string;
  on_promo?: boolean;
  q?: string;
  limit?: number;
  offset?: number;
}

export const getBrowseTree = (signal?: AbortSignal): Promise<BrowseTree> =>
  http.get<BrowseTree>('/categories/browse-tree', { signal }).then(r => r.data);

export interface DominantCategory extends CategoryRef { share: number }

/** SU11A-68: the node most of a result page shares (null = none). At most 60 barcodes. */
export const getDominantCategory = (codes: string[], signal?: AbortSignal): Promise<DominantCategory | null> =>
  http.get<{ category: DominantCategory | null }>('/categories/dominant', {
    params: { code: codes.slice(0, 60) },   // the shared serializer repeats code=...
    signal,
  }).then(r => r.data.category);

export const getCategoryItems = (id: string, params: CategoryItemsParams, signal?: AbortSignal): Promise<CategoryItemsResult> =>
  http.get<CategoryItemsResult>(`/categories/${encodeURIComponent(id)}/items`, { params, signal }).then(r => r.data);
