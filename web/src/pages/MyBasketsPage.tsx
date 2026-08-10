import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Trash2, ShoppingCart, RefreshCw } from 'lucide-react';
import { useAuth } from '../components/AuthContext';
import { useBasket } from '../components/BasketContext';
import { getSavedBaskets, getSavedBasket, deleteSavedBasket } from '../api/client';
import type { SavedBasketSummary } from '../api/client';

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('he-IL', { day: 'numeric', month: 'short', year: 'numeric' });
}

export default function MyBasketsPage() {
  const { user, isLoading: authLoading } = useAuth();
  const { addItem, clearBasket }         = useBasket();
  const navigate                         = useNavigate();

  const [baskets,  setBaskets]  = useState<SavedBasketSummary[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [loading2, setLoading2] = useState<number | null>(null); // loading basket to apply

  // Redirect if not logged in
  useEffect(() => {
    if (!authLoading && !user) navigate('/login');
  }, [user, authLoading, navigate]);

  useEffect(() => {
    if (!user) return;
    getSavedBaskets()
      .then(setBaskets)
      .catch(() => setError('שגיאה בטעינת הסלים'))
      .finally(() => setLoading(false));
  }, [user]);

  const handleLoad = async (id: number) => {
    setLoading2(id);
    try {
      const full = await getSavedBasket(id);
      clearBasket();
      full.items.forEach(item =>
        addItem({ item_code: item.barcode, item_name: item.name, is_weighted: false }),
      );
      navigate('/');
    } catch {
      setError('שגיאה בטעינת הסל');
    } finally {
      setLoading2(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('למחוק את הסל?')) return;
    setDeleting(id);
    try {
      await deleteSavedBasket(id);
      setBaskets(prev => prev.filter(b => b.id !== id));
    } catch {
      setError('שגיאה במחיקת הסל');
    } finally {
      setDeleting(null);
    }
  };

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-500 text-sm">טוען…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">
      <main className="max-w-2xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">הסלים שלי</h1>

        {error && (
          <p className="mb-4 text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {baskets.length === 0 ? (
          <div className="text-center py-16">
            <ShoppingCart size={40} className="text-gray-200 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">אין סלים שמורים</p>
            <p className="text-gray-500 text-sm mt-1 mb-4">
              הוסיפו מוצרים לסל ולחצו "שמור סל" כדי לשמור
            </p>
            <button
              onClick={() => navigate('/')}
              className="px-4 py-2 bg-emerald-700 text-white rounded-lg text-sm font-medium
                         hover:bg-emerald-800 transition-colors"
            >
              לחיפוש מוצרים
            </button>
          </div>
        ) : (
          <ul className="space-y-3">
            {baskets.map(b => (
              <li
                key={b.id}
                className="bg-white rounded-xl border border-gray-200 px-4 py-3
                           flex items-center justify-between gap-3 shadow-sm"
              >
                <div className="min-w-0">
                  <p className="font-semibold text-gray-900 truncate">{b.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {b.item_count} פריטים · עודכן {fmtDate(b.updated_at)}
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={() => handleLoad(b.id)}
                    disabled={loading2 === b.id}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                               bg-emerald-50 text-emerald-700 border border-emerald-200
                               hover:bg-emerald-100 disabled:opacity-50 transition-colors"
                  >
                    <RefreshCw size={12} className={loading2 === b.id ? 'animate-spin' : ''} />
                    טען
                  </button>
                  <button
                    onClick={() => handleDelete(b.id)}
                    disabled={deleting === b.id}
                    className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium
                               bg-white text-gray-500 border border-gray-200
                               hover:bg-rose-50 hover:text-rose-600 hover:border-rose-200
                               disabled:opacity-50 transition-colors"
                  >
                    <Trash2 size={12} />
                    מחק
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
