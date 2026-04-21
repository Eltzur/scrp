import { ShoppingCart } from 'lucide-react';

export default function Header() {
  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShoppingCart className="text-emerald-600" size={22} />
          <span className="font-semibold text-gray-900 text-lg tracking-tight">
            Israeli Price Comparison
          </span>
        </div>
        <div className="text-xs text-gray-400">
          {/* language toggle placeholder — session 6b */}
        </div>
      </div>
    </header>
  );
}
