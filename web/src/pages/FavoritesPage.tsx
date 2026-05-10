import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Star } from 'lucide-react';
import { useAuth } from '../components/AuthContext';
import { getFavorites, getProduct } from '../api/client';
import type { ProductWithPrices } from '../api/client';
import ProductCard from '../components/ProductCard';

export default function FavoritesPage() {
  const { user, isLoading: authLoading } = useAuth();
  const navigate                          = useNavigate();

  const [products, setProducts] = useState<ProductWithPrices[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState<string | null>(null);

  // Redirect if not logged in
  useEffect(() => {
    if (!authLoading && !user) navigate('/login');
  }, [user, authLoading, navigate]);

  useEffect(() => {
    if (!user) return;
    getFavorites()
      .then(async (favs) => {
        if (favs.length === 0) {
          setProducts([]);
          setLoading(false);
          return;
        }
        // Fetch full price data for each favorited barcode in parallel
        const results = await Promise.allSettled(
          favs.map(f => getProduct(f.barcode)),
        );
        setProducts(
          results
            .filter((r): r is PromiseFulfilledResult<ProductWithPrices> => r.status === 'fulfilled')
            .map(r => r.value),
        );
        setLoading(false);
      })
      .catch(() => {
        setError('שגיאה בטעינת המועדפים');
        setLoading(false);
      });
  }, [user]);

  if (authLoading || loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <p className="text-gray-400 text-sm">טוען…</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">
      <main className="max-w-6xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">המועדפים שלי</h1>

        {error && (
          <p className="mb-4 text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
            {error}
          </p>
        )}

        {products.length === 0 ? (
          <div className="text-center py-16">
            <Star size={40} className="text-gray-200 mx-auto mb-3" />
            <p className="text-gray-500 font-medium">עדיין לא סימנת מוצרים מועדפים.</p>
            <p className="text-gray-400 text-sm mt-1 mb-4">
              לחצו על הכוכב ליד כל מוצר בחיפוש
            </p>
            <button
              onClick={() => navigate('/')}
              className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium
                         hover:bg-emerald-700 transition-colors"
            >
              לחיפוש מוצרים
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {products.map(p => (
              <ProductCard key={p.product.item_code} item={p} />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
