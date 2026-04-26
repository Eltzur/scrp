import { Check, ShoppingCart } from 'lucide-react';
import { useBasket } from './BasketContext';

interface Props {
  item_code: string;
  item_name: string | null;
  is_weighted: boolean;
}

export default function BasketButton({ item_code, item_name, is_weighted }: Props) {
  const { items, addItem, removeItem } = useBasket();
  const inBasket = items.some(i => i.item_code === item_code);

  return inBasket ? (
    <button
      onClick={e => { e.stopPropagation(); removeItem(item_code); }}
      className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium
                 bg-emerald-100 text-emerald-700 border border-emerald-300
                 hover:bg-rose-50 hover:text-rose-600 hover:border-rose-200 transition-colors"
    >
      <Check size={11} />
      בסל
    </button>
  ) : (
    <button
      onClick={e => { e.stopPropagation(); addItem({ item_code, item_name, is_weighted }); }}
      className="flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium
                 bg-white text-gray-500 border border-gray-200
                 hover:bg-emerald-50 hover:text-emerald-700 hover:border-emerald-300 transition-colors"
    >
      <ShoppingCart size={11} />
      הוסף לסל
    </button>
  );
}
