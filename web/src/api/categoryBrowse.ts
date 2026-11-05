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
  items: (ProductWithPrices & { category_id: string | null })[];
}

export interface CategoryItemsParams {
  city?: string;
  chain?: string;
  sort?: string;
  on_promo?: boolean;
  limit?: number;
  offset?: number;
}

export const getBrowseTree = (signal?: AbortSignal): Promise<BrowseTree> =>
  http.get<BrowseTree>('/categories/browse-tree', { signal }).then(r => r.data);

export const getCategoryItems = (id: string, params: CategoryItemsParams, signal?: AbortSignal): Promise<CategoryItemsResult> =>
  http.get<CategoryItemsResult>(`/categories/${encodeURIComponent(id)}/items`, { params, signal }).then(r => r.data);
