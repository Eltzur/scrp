import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  X, Trash2, Plus, Minus, ShoppingCart, ArrowRight, Loader2, Save,
} from 'lucide-react';
import { toast } from 'sonner';
import { useBasket } from './BasketContext';
import { useAuth } from './AuthContext';
import { useChains, useCities } from '../api/hooks';
import { compareBasket, createSavedBasket } from '../api/client';
import type { BasketCompareResponse } from '../api/client';
import BasketResults from './BasketResults';

type View = 'basket' | 'results';

export default function BasketDrawer() {
  const { items, isOpen, setIsOpen, removeItem, updateQuantity, clearBasket } = useBasket();
  const { user }                          = useAuth();
  const navigate                          = useNavigate();
  const { data: chains = [] } = useChains();
  const { data: cities = [] } = useCities();

  const [view, setView]                   = useState<View>('basket');
  const [selectedChains, setSelectedChains] = useState<string[]>([]);
  const [selectedCities, setSelectedCities] = useState<string[]>([]);
  const [result, setResult]               = useState<BasketCompareResponse | null>(null);
  const [isComparing, setIsComparing]     = useState(false);
  const [compareError, setCompareError]   = useState<string | null>(null);

  // Save basket
  const [savePromptOpen, setSavePromptOpen] = useState(false);
  const [basketName,     setBasketName]     = useState('');
  const [isSaving,       setIsSaving]       = useState(false);

  const qtyStep = (weighted: boolean) => weighted ? 100 : 1;
  const qtyLabel = (qty: number, weighted: boolean) => weighted ? `${qty}g` : String(qty);

  const toggleChain = (id: string) =>
    setSelectedChains(prev => prev.includes(id) ? prev.filter(c => c !== id) : [...prev, id]);

  const handleCompare = async () => {
    if (!items.length) return;
    setIsComparing(true);
    setCompareError(null);
    try {
      const res = await compareBasket({
        items: items.map(i => ({ item_code: i.item_code, quantity: i.quantity })),
        chain_ids: selectedChains.length ? selectedChains : null,
        cities:    selectedCities.length ? selectedCities : null,
      });
      setResult(res);
      setView('results');
    } catch (e: unknown) {
      const detail = (e as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail;
      setCompareError(detail ?? 'שגיאה בהשוואה');
    } finally {
      setIsComparing(false);
    }
  };

  const handleSave = async () => {
    if (!basketName.trim()) return;
    setIsSaving(true);
    try {
      await createSavedBasket({
        name:  basketName.trim(),
        items: items.map(i => ({ barcode: i.item_code, name: i.item_name ?? '', qty: i.quantity })),
      });
      toast('שמירת סל הצליחה');
      setSavePromptOpen(false);
      setBasketName('');
      navigate('/baskets');
    } catch {
      toast('שגיאה בשמירת הסל');
    } finally {
      setIsSaving(false);
    }
  };

  const handleClose = () => { setIsOpen(false); setView('basket'); };

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/30 z-40" onClick={handleClose} />

      {/* Panel — always on physical right edge */}
      <div className="fixed inset-y-0 right-0 z-50 w-full max-w-md bg-white shadow-2xl flex flex-col" dir="rtl">

        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 shrink-0">
          <div className="flex items-center gap-2">
            <ShoppingCart size={18} className="text-emerald-600" />
            <span className="font-semibold text-gray-900 text-sm">
              {view === 'results' ? 'תוצאות השוואה' : 'הסל שלי'}
            </span>
            {view === 'basket' && items.length > 0 && (
              <span className="text-xs text-gray-400">{items.length} מוצרים</span>
            )}
          </div>
          <div className="flex items-center gap-3">
            {view === 'results' && (
              <button
                onClick={() => setView('basket')}
                className="flex items-center gap-1 text-xs text-emerald-600 hover:text-emerald-800 font-medium"
              >
                <ArrowRight size={13} />
                חזור לסל
              </button>
            )}
            {view === 'basket' && items.length > 0 && (
              <button onClick={clearBasket} className="text-xs text-gray-400 hover:text-rose-500 transition-colors">
                נקה
              </button>
            )}
            <button onClick={handleClose} className="p-1 text-gray-400 hover:text-gray-600">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Save basket bar — visible only in basket view with items */}
        {view === 'basket' && items.length > 0 && (
          <div className="px-4 py-2 border-b border-gray-100 shrink-0">
            {!savePromptOpen ? (
              user ? (
                <button
                  onClick={() => setSavePromptOpen(true)}
                  className="flex items-center gap-1.5 text-xs font-medium text-emerald-700
                             hover:text-emerald-800 transition-colors"
                >
                  <Save size={13} />
                  שמור סל
                </button>
              ) : (
                <span
                  title="התחברו כדי לשמור סלים"
                  className="flex items-center gap-1.5 text-xs font-medium text-gray-300 cursor-not-allowed select-none"
                >
                  <Save size={13} />
                  שמור סל
                </span>
              )
            ) : (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={basketName}
                  onChange={e => setBasketName(e.target.value)}
                  placeholder="שם הסל…"
                  onKeyDown={e => e.key === 'Enter' && handleSave()}
                  className="flex-1 text-xs px-2 py-1 border border-gray-300 rounded-lg
                             focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  autoFocus
                />
                <button
                  onClick={handleSave}
                  disabled={isSaving || !basketName.trim()}
                  className="text-xs px-3 py-1 bg-emerald-600 text-white rounded-lg
                             hover:bg-emerald-700 disabled:opacity-50 transition-colors"
                >
                  {isSaving ? '…' : 'שמור'}
                </button>
                <button
                  onClick={() => { setSavePromptOpen(false); setBasketName(''); }}
                  className="text-xs text-gray-400 hover:text-gray-600"
                >
                  <X size={14} />
                </button>
              </div>
            )}
          </div>
        )}

        {view === 'basket' ? (
          <>
            {/* Items */}
            <div className="flex-1 overflow-y-auto">
              {items.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full min-h-[200px] text-center px-4">
                  <ShoppingCart size={36} className="text-gray-200 mb-3" />
                  <p className="text-sm text-gray-400 font-medium">הסל ריק</p>
                  <p className="text-xs text-gray-300 mt-1">הוסיפו מוצרים מתוצאות החיפוש</p>
                </div>
              ) : (
                <ul className="px-4 py-2 space-y-1">
                  {items.map(item => (
                    <li key={item.item_code}
                        className="flex items-center gap-2 py-2.5 border-b border-gray-100 last:border-0">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-800 truncate leading-snug" dir="auto">
                          {item.item_name || item.item_code}
                        </p>
                        <p className="text-xs text-gray-300 font-mono">{item.item_code}</p>
                      </div>
                      {/* Quantity controls */}
                      <div className="flex items-center gap-1 shrink-0" dir="ltr">
                        <button
                          onClick={() => updateQuantity(item.item_code, item.quantity - qtyStep(item.is_weighted))}
                          className="w-6 h-6 flex items-center justify-center rounded-md border border-gray-200
                                     text-gray-500 hover:border-gray-400 transition-colors"
                        >
                          <Minus size={10} />
                        </button>
                        <span className="w-10 text-center text-xs font-medium text-gray-700">
                          {qtyLabel(item.quantity, item.is_weighted)}
                        </span>
                        <button
                          onClick={() => updateQuantity(item.item_code, item.quantity + qtyStep(item.is_weighted))}
                          className="w-6 h-6 flex items-center justify-center rounded-md border border-gray-200
                                     text-gray-500 hover:border-gray-400 transition-colors"
                        >
                          <Plus size={10} />
                        </button>
                      </div>
                      <button
                        onClick={() => removeItem(item.item_code)}
                        className="p-1 text-gray-300 hover:text-rose-500 transition-colors shrink-0"
                      >
                        <Trash2 size={14} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {/* Filters + compare */}
            {items.length > 0 && (
              <div className="border-t border-gray-200 px-4 py-3 space-y-3 shrink-0">
                {/* Chain filter chips */}
                <div>
                  <p className="text-xs font-medium text-gray-500 mb-1.5">
                    רשתות
                    {selectedChains.length === 0 && (
                      <span className="text-gray-300 font-normal"> · כל הרשתות</span>
                    )}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {chains.map(c => (
                      <button
                        key={c.chain_id}
                        onClick={() => toggleChain(c.chain_id)}
                        className={`px-2.5 py-0.5 rounded-full text-xs border transition-colors
                          ${selectedChains.includes(c.chain_id)
                            ? 'bg-emerald-600 text-white border-emerald-600'
                            : 'bg-white text-gray-600 border-gray-200 hover:border-emerald-400'}`}
                      >
                        {c.name}
                      </button>
                    ))}
                  </div>
                </div>

                {/* City filter */}
                <div>
                  <p className="text-xs font-medium text-gray-500 mb-1.5">
                    עיר
                    {selectedCities.length === 0 && (
                      <span className="text-gray-300 font-normal"> · כל הערים</span>
                    )}
                  </p>
                  <div className="flex gap-2 items-start">
                    <select
                      multiple
                      value={selectedCities}
                      onChange={e =>
                        setSelectedCities(Array.from(e.target.selectedOptions, o => o.value))
                      }
                      className="flex-1 text-sm border border-gray-200 rounded-lg px-2 py-1.5 h-20
                                 focus:outline-none focus:ring-2 focus:ring-emerald-500 text-gray-700"
                      dir="rtl"
                    >
                      {[...cities]
                        .sort((a, b) => a.city.localeCompare(b.city, 'he'))
                        .map(c => (
                          <option key={c.city} value={c.city}>{c.city}</option>
                        ))}
                    </select>
                    {selectedCities.length > 0 && (
                      <button
                        onClick={() => setSelectedCities([])}
                        className="text-xs text-gray-400 hover:text-rose-500 mt-1"
                      >
                        נקה
                      </button>
                    )}
                  </div>
                </div>

                {compareError && (
                  <p className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
                    {compareError}
                  </p>
                )}

                <button
                  onClick={handleCompare}
                  disabled={isComparing}
                  className="w-full py-2.5 bg-emerald-600 text-white rounded-xl text-sm font-semibold
                             hover:bg-emerald-700 disabled:opacity-60 disabled:cursor-not-allowed
                             transition-colors flex items-center justify-center gap-2"
                >
                  {isComparing ? (
                    <><Loader2 size={16} className="animate-spin" /> משווה…</>
                  ) : (
                    <><ShoppingCart size={16} /> השווה סל 🛒</>
                  )}
                </button>
              </div>
            )}
          </>
        ) : (
          <div className="flex-1 overflow-y-auto">
            {result && <BasketResults result={result} basketItems={items} />}
          </div>
        )}
      </div>
    </>
  );
}
