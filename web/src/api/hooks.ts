import { useQuery } from '@tanstack/react-query';
import {
  searchProducts,
  compareProducts,
  getProduct,
  getChains,
  getCities,
  getStats,
  type SearchOpts,
  type CompareOpts,
} from './client';

const STALE = 5 * 60 * 1000; // 5 minutes

export const useSearch = (query: string, opts: SearchOpts = {}, enabled = true) =>
  useQuery({
    queryKey: ['search', query, opts],
    queryFn: () => searchProducts(query, opts),
    enabled: enabled && query.trim().length >= 2,
    staleTime: STALE,
    refetchOnWindowFocus: false,
    placeholderData: prev => prev,
  });

export const useCompare = (query: string, opts: CompareOpts = {}, enabled = true) =>
  useQuery({
    queryKey: ['compare', query, opts],
    queryFn: () => compareProducts(query, opts),
    enabled: enabled && query.trim().length >= 2,
    staleTime: STALE,
    refetchOnWindowFocus: false,
    placeholderData: prev => prev,
  });

export const useProduct = (barcode: string) =>
  useQuery({
    queryKey: ['product', barcode],
    queryFn: () => getProduct(barcode),
    enabled: !!barcode,
    staleTime: STALE,
    refetchOnWindowFocus: false,
  });

export const useChains = () =>
  useQuery({
    queryKey: ['chains'],
    queryFn: getChains,
    staleTime: STALE,
    refetchOnWindowFocus: false,
  });

export const useCities = () =>
  useQuery({
    queryKey: ['cities'],
    queryFn: getCities,
    staleTime: STALE,
    refetchOnWindowFocus: false,
  });

export const useStats = () =>
  useQuery({
    queryKey: ['stats'],
    queryFn: getStats,
    staleTime: STALE,
    refetchOnWindowFocus: false,
  });
