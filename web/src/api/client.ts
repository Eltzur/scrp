import axios from 'axios';
import type { components } from '../types/api';

export type ChainSummary = components['schemas']['ChainSummary'];
export type Store = components['schemas']['Store'];
export type PriceQuote = components['schemas']['PriceQuote'];
export type Product = components['schemas']['Product'];
export type ProductWithPrices = components['schemas']['ProductWithPrices'];
export type SearchResult = components['schemas']['SearchResult'];
export type StatsResponse = components['schemas']['StatsResponse'];

const http = axios.create({ baseURL: 'http://localhost:8000' });

export interface SearchOpts {
  limit?: number;
  city?: string | null;
  chain?: string | null;
}

export interface CompareOpts {
  limit?: number;
  city?: string | null;
}

export const searchProducts = (q: string, opts: SearchOpts = {}): Promise<SearchResult> =>
  http.get<SearchResult>('/search', { params: { q, ...opts } }).then(r => r.data);

export const compareProducts = (q: string, opts: CompareOpts = {}): Promise<SearchResult> =>
  http.get<SearchResult>('/compare', { params: { q, ...opts } }).then(r => r.data);

export const getProduct = (barcode: string): Promise<ProductWithPrices> =>
  http.get<ProductWithPrices>(`/product/${barcode}`).then(r => r.data);

export const getChains = (): Promise<ChainSummary[]> =>
  http.get<ChainSummary[]>('/chains').then(r => r.data);

export const getCities = (): Promise<string[]> =>
  http.get<string[]>('/cities').then(r => r.data);

export const getStores = (opts: { chain?: string; city?: string } = {}): Promise<Store[]> =>
  http.get<Store[]>('/stores', { params: opts }).then(r => r.data);

export const getStats = (): Promise<StatsResponse> =>
  http.get<StatsResponse>('/stats').then(r => r.data);
