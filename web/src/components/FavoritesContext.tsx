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
      was ? next.delete(barcode) : next.add(barcode);
      return next;
    });

    try {
      const result = await apiToggle(barcode);
      // Sync with server truth
      setFavorited(prev => {
        const next = new Set(prev);
        result.favorited ? next.add(barcode) : next.delete(barcode);
        return next;
      });
    } catch {
      // Revert on error
      setFavorited(prev => {
        const next = new Set(prev);
        was ? next.add(barcode) : next.delete(barcode);
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

export function useFavorites() {
  const ctx = useContext(FavoritesContext);
  if (!ctx) throw new Error('useFavorites must be inside FavoritesProvider');
  return ctx;
}
