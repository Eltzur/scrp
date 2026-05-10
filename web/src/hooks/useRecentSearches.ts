import { useState } from 'react';

const MAX    = 10;
const LS_KEY = 'xxl_recent_searches';

function load(): string[] {
  try { return JSON.parse(localStorage.getItem(LS_KEY) ?? '[]'); }
  catch { return []; }
}

function save(searches: string[]): void {
  localStorage.setItem(LS_KEY, JSON.stringify(searches));
}

export function useRecentSearches() {
  const [recentSearches, setRecentSearches] = useState<string[]>(load);

  const addSearch = (query: string) => {
    const q = query.trim();
    if (q.length < 2) return;
    setRecentSearches(prev => {
      const deduped = [q, ...prev.filter(s => s.toLowerCase() !== q.toLowerCase())].slice(0, MAX);
      save(deduped);
      return deduped;
    });
  };

  const removeSearch = (query: string) => {
    setRecentSearches(prev => {
      const updated = prev.filter(s => s !== query);
      save(updated);
      return updated;
    });
  };

  const clearAll = () => {
    localStorage.removeItem(LS_KEY);
    setRecentSearches([]);
  };

  return { recentSearches, addSearch, removeSearch, clearAll };
}
