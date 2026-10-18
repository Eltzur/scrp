import {
  createContext, useContext, useEffect, useState,
  type ReactNode,
} from 'react';
import { useAuth } from './AuthContext';
import {
  toggleFavorite as apiToggle,
  removeFavorite as apiRemove,
  getFavorites,
} from '../api/client';

interface FavoritesContextType {
  favoritedBarcodes: Set<string>;
  isFavorited:       (barcode: string) => boolean;
  toggleFavorite:    (barcode: string) => Promise<void>;
  removeFavorite:    (barcode: string) => Promise<void>;
  favoritesCount:    number;
}

const FavoritesContext = createContext<FavoritesContextType | null>(null);

export function FavoritesProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [favoritedBarcodes, setFavorited] = useState<Set<string>>(new Set());

  // Load favorites on login, clear on logout
  useEffect(() => {
    if (!user) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clears the set on sign-out; the load path sets it in a callback
      setFavorited(new Set());
      return;
    }
    getFavorites()
      .then(items => setFavorited(new Set(items.map(i => i.barcode))))
      .catch(() => {}); // silent — user can still toggle
  }, [user]);

  const isFavorited = (barcode: string) => favoritedBarcodes.has(barcode);
  const favoritesCount = favoritedBarcodes.size;

  const toggleFavorite = async (barcode: string) => {
    const was = favoritedBarcodes.has(barcode);

    // Optimistic update
    setFavorited(prev => {
      const next = new Set(prev);
      if (was) next.delete(barcode); else next.add(barcode);
      return next;
    });

    try {
      const result = await apiToggle(barcode);
      // Sync with server truth
      setFavorited(prev => {
        const next = new Set(prev);
        if (result.favorited) next.add(barcode); else next.delete(barcode);
        return next;
      });
    } catch {
      // Revert on error
      setFavorited(prev => {
        const next = new Set(prev);
        if (was) next.add(barcode); else next.delete(barcode);
        return next;
      });
    }
  };

  const removeFavorite = async (barcode: string) => {
    setFavorited(prev => { const n = new Set(prev); n.delete(barcode); return n; });
    try {
      await apiRemove(barcode);
    } catch {
      setFavorited(prev => { const n = new Set(prev); n.add(barcode); return n; });
    }
  };

  return (
    <FavoritesContext.Provider value={{
      favoritedBarcodes, isFavorited, toggleFavorite, removeFavorite, favoritesCount,
    }}>
      {children}
    </FavoritesContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components -- the hook lives next to its provider; fast refresh reloads this file fully
export function useFavorites() {
  const ctx = useContext(FavoritesContext);
  if (!ctx) throw new Error('useFavorites must be inside FavoritesProvider');
  return ctx;
}
