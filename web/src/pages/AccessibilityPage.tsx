import { Link } from 'react-router-dom';
import XxlLogo from '../components/XxlLogo';
import Footer from '../components/Footer';

export default function AccessibilityPage() {
  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">

      {/* Header strip */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-2 flex items-center justify-between">
          <Link to="/">
            <XxlLogo variant="header" lang="he" className="h-10" />
          </Link>
          <Link to="/" className="text-sm text-emerald-600 hover:underline">
            ← חזרה לדף הבית
          </Link>
        </div>
      </header>

      {/* Body */}
      <main className="max-w-3xl mx-auto px-4 py-10">
        <div className="bg-white rounded-2xl border border-gray-200 p-6 md:p-8">

          <h1 className="text-3xl font-bold text-[#022C22]">הצהרת נגישות</h1>

          <div className="mt-8 space-y-6 text-gray-700 leading-relaxed">
            <p>
              XXL אנטרפרייזס פועלת מתוך מחויבות להנגשת האתר והאפליקציה לכלל המשתמשים, לרבות אנשים
              עם מוגבלות. אנו פועלים באופן שוטף לשפר את חווית השימוש ולהתאימה, ככל הניתן, לתקן
              הישראלי ת"י 5568 ולהנחיות הנגישות הבינלאומיות WCAG 2.0 ברמה AA.
            </p>

            <p>
              נתקלתם בבעיית נגישות באתר או באפליקציה? נשמח לשמוע ולטפל בפנייתכם בהקדם:{' '}
              <a href="mailto:info@xxl.co.il" className="text-emerald-700 hover:underline">
                info@xxl.co.il
              </a>
            </p>

            <p className="text-sm text-gray-500">עודכן לאחרונה: 10 באוגוסט 2026</p>
          </div>

          <div className="mt-10">
            <Link to="/" className="text-sm text-emerald-600 hover:underline">← חזרה לדף הבית</Link>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
