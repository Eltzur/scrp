import {
  createContext, useContext, useEffect, useRef, useState,
  type ReactNode,
} from 'react';

export interface BasketEntry {
  item_code: string;
  item_name: string | null;
  quantity: number;   // count for normal items; grams (100g steps) for weighted
  is_weighted: boolean;
}

interface BasketContextType {
  items: BasketEntry[];
  isOpen: boolean;
  warning: string | null;
  setIsOpen: (open: boolean) => void;
  addItem: (entry: Omit<BasketEntry, 'quantity'>) => void;
  removeItem: (item_code: string) => void;
  updateQuantity: (item_code: string, qty: number) => void;
  clearBasket: () => void;
}

export const BASKET_LIMIT = 25;
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
  const [isOpen, setIsOpen]   = useState(false);
  const [warning, setWarning] = useState<string | null>(null);
  const warnRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    localStorage.setItem(LS_KEY, JSON.stringify(items));
  }, [items]);

  const showWarning = (msg: string) => {
    setWarning(msg);
    if (warnRef.current) clearTimeout(warnRef.current);
    warnRef.current = setTimeout(() => setWarning(null), 3000);
  };

  const addItem = (entry: Omit<BasketEntry, 'quantity'>) => {
    setItems(prev => {
      const existing = prev.find(i => i.item_code === entry.item_code);
      if (existing) {
        const step = existing.is_weighted ? 100 : 1;
        return prev.map(i =>
          i.item_code === entry.item_code ? { ...i, quantity: i.quantity + step } : i
        );
      }
      if (prev.length >= BASKET_LIMIT) {
        showWarning(`הסל מוגבל ל-${BASKET_LIMIT} מוצרים שונים`);
        return prev;
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
      items, isOpen, warning, setIsOpen,
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
