import {
  createContext, useContext, useEffect, useState,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

export interface BasketEntry {
  item_code: string;
  item_name: string | null;
  quantity: number;   // count for normal items; grams (100g steps) for weighted
  is_weighted: boolean;
}

interface BasketContextType {
  items: BasketEntry[];
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  addItem: (entry: Omit<BasketEntry, 'quantity'>) => void;
  removeItem: (item_code: string) => void;
  updateQuantity: (item_code: string, qty: number) => void;
  clearBasket: () => void;
}

export const FREE_TIER_LIMIT = 25;
const LS_KEY = 'basket_items';

const BasketContext = createContext<BasketContextType | null>(null);

export function BasketProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<BasketEntry[]>(() => {
    try {
      const stored = localStorage.getItem(LS_KEY);
      return stored ? (JSON.parse(stored) as BasketEntry[]) : [];
    } catch {
      return [];
    }
  });
  const [isOpen, setIsOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    localStorage.setItem(LS_KEY, JSON.stringify(items));
  }, [items]);

  const addItem = (entry: Omit<BasketEntry, 'quantity'>) => {
    const existing = items.find(i => i.item_code === entry.item_code);

    if (!existing && items.length >= FREE_TIER_LIMIT) {
      toast(
        'סל הקניות מוגבל ל-25 פריטים למשתמשים לא רשומים. אנא הירשמו כדי להנות מסל גדול יותר והטבות נוספות',
        {
          icon: '🔒',
          action: {
            label: 'להרשמה',
            onClick: () => navigate('/signup'),
          },
          style: {
            background: '#059669',
            color: '#ffffff',
          },
          actionButtonStyle: {
            background: '#ffffff',
            color: '#059669',
            fontWeight: '600',
          },
        },
      );
      return;
    }

    setItems(prev => {
      if (existing) {
        const step = existing.is_weighted ? 100 : 1;
        return prev.map(i =>
          i.item_code === entry.item_code ? { ...i, quantity: i.quantity + step } : i,
        );
      }
      return [...prev, { ...entry, quantity: entry.is_weighted ? 100 : 1 }];
    });
  };

  const removeItem = (item_code: string) =>
    setItems(prev => prev.filter(i => i.item_code !== item_code));

  const updateQuantity = (item_code: string, qty: number) => {
    if (qty <= 0) { removeItem(item_code); return; }
    setItems(prev => prev.map(i => i.item_code === item_code ? { ...i, quantity: qty } : i));
  };

  const clearBasket = () => setItems([]);

  return (
    <BasketContext.Provider value={{
      items, isOpen, setIsOpen,
      addItem, removeItem, updateQuantity, clearBasket,
    }}>
      {children}
    </BasketContext.Provider>
  );
}

export function useBasket() {
  const ctx = useContext(BasketContext);
  if (!ctx) throw new Error('useBasket must be inside BasketProvider');
  return ctx;
}
