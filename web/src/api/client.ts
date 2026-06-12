import axios from 'axios';
import type { components } from '../types/api';

export type ChainSummary    = components['schemas']['ChainSummary'];
export type Store           = components['schemas']['Store'];
export type PriceQuote      = components['schemas']['PriceQuote'];
export type Product         = components['schemas']['Product'];
export type ProductWithPrices = components['schemas']['ProductWithPrices'];
export type SearchResult    = components['schemas']['SearchResult'];
export type StatsResponse   = components['schemas']['StatsResponse'];
export type CityInfo        = components['schemas']['CityInfo'];

import { supabase } from '../lib/supabase';

const http = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  paramsSerializer: (params) => {
    const sp = new URLSearchParams();
    for (const [key, val] of Object.entries(params)) {
      if (Array.isArray(val)) {
        val.forEach(v => sp.append(key, String(v)));
      } else if (val != null) {
        sp.set(key, String(val));
      }
    }
    return sp.toString();
  },
});

// Attach Supabase access token to every request when the user is logged in
http.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession();
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`;
  }
  return config;
});

export interface SearchOpts {
  limit?: number;
  offset?: number;
  city?: string[] | null;
  chain?: string[] | null;
  group_by?: 'chain' | 'store';
}

export interface CompareOpts {
  limit?: number;
  offset?: number;
  city?: string[] | null;
}

export const searchProducts = (q: string, opts: SearchOpts = {}): Promise<SearchResult> =>
  http.get<SearchResult>('/search', { params: { q, ...opts } }).then(r => r.data);

export const compareProducts = (q: string, opts: CompareOpts = {}): Promise<SearchResult> =>
  http.get<SearchResult>('/compare', { params: { q, ...opts } }).then(r => r.data);

export const getProduct = (barcode: string): Promise<ProductWithPrices> =>
  http.get<ProductWithPrices>(`/product/${barcode}`).then(r => r.data);

export const getChains = (): Promise<ChainSummary[]> =>
  http.get<ChainSummary[]>('/chains').then(r => r.data);

export const getCities = (): Promise<CityInfo[]> =>
  http.get<CityInfo[]>('/cities').then(r => r.data);

export const getStores = (opts: { chain?: string; city?: string } = {}): Promise<Store[]> =>
  http.get<Store[]>('/stores', { params: opts }).then(r => r.data);

export const getStats = (): Promise<StatsResponse> =>
  http.get<StatsResponse>('/stats').then(r => r.data);

export interface ChainFreshness {
  chain_name: string;
  last_loaded_at: string | null;
}

export interface FreshnessResponse {
  oldest_last_loaded_at: string | null;
  chains: ChainFreshness[];
}

export const getFreshness = (): Promise<FreshnessResponse> =>
  http.get<FreshnessResponse>('/freshness').then(r => r.data);

// ---------------------------------------------------------------------------
// Saved basket API
// ---------------------------------------------------------------------------

export interface SavedBasketSummary {
  id:         number;
  name:       string;
  item_count: number;
  updated_at: string;
}

export interface SavedBasketFull {
  id:         number;
  name:       string;
  items:      { barcode: string; name: string; qty: number }[];
  created_at: string;
  updated_at: string;
}

export const getSavedBaskets = (): Promise<SavedBasketSummary[]> =>
  http.get<SavedBasketSummary[]>('/baskets').then(r => r.data);

export const getSavedBasket = (id: number): Promise<SavedBasketFull> =>
  http.get<SavedBasketFull>(`/baskets/${id}`).then(r => r.data);

export const createSavedBasket = (body: {
  name: string;
  items: { barcode: string; name: string; qty: number }[];
}): Promise<SavedBasketFull> =>
  http.post<SavedBasketFull>('/baskets', body).then(r => r.data);

export const deleteSavedBasket = (id: number): Promise<void> =>
  http.delete(`/baskets/${id}`).then(() => undefined);

// ---------------------------------------------------------------------------
// Favorites API
// ---------------------------------------------------------------------------

export interface FavoriteItem {
  barcode:    string;
  item_name:  string | null;
  created_at: string;
}

export const toggleFavorite = (barcode: string): Promise<{ favorited: boolean }> =>
  http.post<{ favorited: boolean }>(`/favorites/${barcode}`).then(r => r.data);

export const getFavorites = (): Promise<FavoriteItem[]> =>
  http.get<FavoriteItem[]>('/favorites').then(r => r.data);

export const removeFavorite = (barcode: string): Promise<void> =>
  http.delete(`/favorites/${barcode}`).then(() => undefined);

// ---------------------------------------------------------------------------
// Basket types (defined here; not yet in generated types/api.ts)
// ---------------------------------------------------------------------------

export interface BasketBreakdownItem {
  item_code: string;
  item_name: string | null;
  price: number | null;
  quantity: number;
  subtotal: number | null;
  found: boolean;
}

export interface BasketChainResult {
  chain_id: string;
  chain_name: string | null;
  total_price: number;
  items_found: number;
  items_missing: number;
  breakdown: BasketBreakdownItem[];
}

export interface BasketCompareResponse {
  chains: BasketChainResult[];
  winner_chain_id: string | null;
  item_limit: number;
  items_requested: number;
}

export const compareBasket = (body: {
  items: { item_code: string; quantity: number }[];
  chain_ids?: string[] | null;
  cities?: string[] | null;
}): Promise<BasketCompareResponse> =>
  http.post<BasketCompareResponse>('/basket/compare', body).then(r => r.data);

// ---------------------------------------------------------------------------
// Promos
// ---------------------------------------------------------------------------

export interface PromoItem {
  item_code: string;
  promo_id: string | null;
  promo_description: string | null;
  promo_type: number | null;
  allow_multiple_discounts: boolean | null;
  min_qty: number | null;
  reward_type: number | null;
  discount_rate: number | null;
  discount_price: number | null;
  min_purchase_amount: number | null;
  promo_start: string | null;
  promo_end: string | null;
  discount_pct: number | null;
}

export const getPromosBulk = (
  stores: { chain_id: string; store_id: string }[],
): Promise<Record<string, PromoItem[]>> =>
  http
    .post<Record<string, PromoItem[]>>('/promos/bulk', { stores })
    .then(r => r.data)
    .catch(() => ({}));
