import { useState } from 'react';
import { cleanSearch, dedupeSearches, pushSearch } from '../utils/recentSearch';

const MAX    = 10;
const LS_KEY = 'xxl_recent_searches';

function save(searches: string[]): void {
  localStorage.setItem(LS_KEY, JSON.stringify(searches));
}

/** SU11A-58: entries saved before normalisation are cleaned and deduped on
 *  load ("זירו 1.5" / "זירו1.5" / "1.5זירו" become one), and saved back. */
function load(): string[] {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(LS_KEY) ?? '[]');
    if (!Array.isArray(stored)) return [];
    const clean = dedupeSearches(stored, MAX);
    if (clean.length !== stored.length || clean.some((q, i) => q !== stored[i])) save(clean);
    return clean;
  } catch { return []; }
}

export function useRecentSearches() {
  const [recentSearches, setRecentSearches] = useState<string[]>(load);

  const addSearch = (query: string) => {
    if (cleanSearch(query).length < 2) return;
    setRecentSearches(prev => {
      const next = pushSearch(prev, query, MAX);
      save(next);
      return next;
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
