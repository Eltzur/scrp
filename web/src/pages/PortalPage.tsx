import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, ShoppingCart, Sun, Shirt, Gift, Clock, Sparkles } from 'lucide-react';
import XxlLogo from '../components/XxlLogo';
import XxlLogoPortal from '../components/XxlLogoPortal';
import Footer from '../components/Footer';
import { classifyAndRoute } from '../utils/portalSearchRouter';

const PLACEHOLDERS = [
  'חפשו: חלב תנובה 3%',
  'חפשו: טיסה לפראג בקיץ',
  'חפשו: מלון באילת לסופ"ש',
  'חפשו: נעלי ניו באלאנס 574',
];

export default function PortalPage() {
  const navigate = useNavigate();
  const [query,          setQuery]          = useState('');
  const [errorHint,      setErrorHint]      = useState('');
  const [placeholderIdx, setPlaceholderIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Rotate placeholder every 3 seconds
  useEffect(() => {
    const id = setInterval(() => {
      setPlaceholderIdx(i => (i + 1) % PLACEHOLDERS.length);
    }, 3000);
    return () => clearInterval(id);
  }, []);

  const handleSubmit = () => {
    const result = classifyAndRoute(query);
    setErrorHint('');
    if (result.intent === 'unknown') {
      setErrorHint('לא הבנו — נסו לחפש מצרך, חופשה או בגד');
      return;
    }
    if (result.intent === 'groceries') {
      window.location.href = result.destination;
    } else {
      navigate(result.destination);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">

      {/* Header strip */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-2 flex items-center justify-between">
          <XxlLogo variant="header" lang="he" className="h-10" />
          <div className="flex items-center gap-3">
            <a href="/login"  className="text-sm text-gray-500 hover:text-gray-700 transition-colors px-2 py-1">
              התחברות
            </a>
            <a href="/signup" className="text-sm font-medium text-emerald-600 hover:text-emerald-700 transition-colors px-3 py-1.5 rounded-lg border border-emerald-600 hover:bg-emerald-50">
              הרשמה
            </a>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="pt-16 md:pt-20 pb-0">
        <div className="max-w-3xl mx-auto px-4 text-center">
          <XxlLogoPortal variant="hero" lang="he" className="w-full max-w-2xl mx-auto" />
          <p className="text-2xl md:text-4xl font-bold text-[#022C22] mt-2 mb-12">
            הפורטל שהופך כסף רגיל לכסף חכם
          </p>
        </div>
      </section>

      {/* Search bar */}
      <section>
        <div className="max-w-2xl mx-auto px-4">
          <div className="flex items-center gap-2 bg-white border-2 border-emerald-600 rounded-2xl shadow-sm p-2 md:p-3">
            <Search size={20} className="text-emerald-600 shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={e => { setQuery(e.target.value); setErrorHint(''); }}
              onKeyDown={e => { if (e.key === 'Enter') handleSubmit(); }}
              placeholder={PLACEHOLDERS[placeholderIdx]}
              className="flex-1 bg-transparent outline-none text-right text-base md:text-lg py-2 text-gray-800 placeholder-gray-400"
              dir="rtl"
            />
            <button
              onClick={handleSubmit}
              className="bg-emerald-600 text-white font-medium rounded-xl px-4 py-2 hover:bg-emerald-700 transition-colors shrink-0"
            >
              חיפוש
            </button>
          </div>
          {errorHint && (
            <p className="text-sm text-orange-600 mt-2 text-right pr-2">{errorHint}</p>
          )}
        </div>
      </section>

      {/* Vertical tiles */}
      <section className="max-w-4xl mx-auto px-4 mt-16">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">

          {/* מצרכים — LIVE */}
          <button
            onClick={() => { window.location.href = 'https://super.xxl.co.il'; }}
            className="bg-white border-2 border-emerald-600 rounded-2xl p-6 text-center hover:shadow-lg hover:-translate-y-1 transition-all relative cursor-pointer"
          >
            <span className="absolute top-3 left-3 bg-emerald-600 text-white text-xs font-medium px-2 py-1 rounded">
              LIVE
            </span>
            <ShoppingCart size={40} className="text-emerald-600 mx-auto" />
            <p className="text-lg font-semibold text-[#022C22] mt-3">מצרכים</p>
            <p className="text-sm text-gray-600 mt-1">השוואת מחירי סופר</p>
          </button>

          {/* חופשות — LIVE */}
          <button
            onClick={() => { window.location.href = 'https://fly.xxl.co.il'; }}
            className="bg-white border-2 border-emerald-600 rounded-2xl p-6 text-center hover:shadow-lg hover:-translate-y-1 transition-all relative cursor-pointer"
          >
            <span className="absolute top-3 left-3 bg-emerald-600 text-white text-xs font-medium px-2 py-1 rounded">
              LIVE
            </span>
            <Sun size={40} className="text-orange-600 mx-auto" />
            <p className="text-lg font-semibold text-[#022C22] mt-3">טיסות</p>
            <p className="text-sm text-gray-600 mt-1">טיסות</p>
          </button>

          {/* אופנה — בקרוב */}
          <button
            onClick={() => navigate('/fashion')}
            className="bg-white border border-gray-200 rounded-2xl p-6 text-center hover:shadow-lg hover:-translate-y-1 transition-all relative cursor-pointer opacity-90"
          >
            <span className="absolute top-3 left-3 bg-orange-600 text-white text-xs font-medium px-2 py-1 rounded">
              בקרוב
            </span>
            <Shirt size={40} className="text-purple-600 mx-auto" />
            <p className="text-lg font-semibold text-[#022C22] mt-3">אופנה</p>
            <p className="text-sm text-gray-600 mt-1">בגדים ונעליים</p>
          </button>
        </div>
      </section>

      {/* Value-props strip */}
      <section className="max-w-4xl mx-auto px-4 mt-16 pb-12 border-t border-gray-200 pt-12">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-center">
          <div>
            <Gift size={24} className="text-emerald-600 mx-auto" />
            <p className="font-medium text-[#022C22] mt-2">חינם לחלוטין</p>
            <p className="text-sm text-gray-600 mt-1">ההשוואה תמיד חינם</p>
          </div>
          <div>
            <Clock size={24} className="text-emerald-600 mx-auto" />
            <p className="font-medium text-[#022C22] mt-2">מחירים בזמן אמת</p>
            <p className="text-sm text-gray-600 mt-1">מתעדכנים מדי יום</p>
          </div>
          <div>
            <Sparkles size={24} className="text-emerald-600 mx-auto" />
            <p className="font-medium text-[#022C22] mt-2">חכם וישראלי</p>
            <p className="text-sm text-gray-600 mt-1">AI שמבין מה אתם מחפשים</p>
          </div>
        </div>
      </section>

      <Footer />
    </div>
  );
}
