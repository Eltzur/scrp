import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Bot, Code, Database, Handshake, Mail } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import XxlLogo from '../components/XxlLogo';
import Footer from '../components/Footer';

// SU11A-40: open invitation to collaborate. Contact is a mailto link only —
// no form, no backend call, nothing stored.
const CONTACT_EMAIL = 'info@xxl.co.il';
const MAILTO_HREF = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent('שיתוף פעולה עם XXL')}`;

const TITLE = 'שיתופי פעולה | XXL';
const DESCRIPTION = 'XXL פתוחה לשיתופי פעולה: נתונים, API, MCP ועוד.';

const TOPICS: { icon: LucideIcon; title: string; text: string }[] = [
  {
    icon: Database,
    title: 'נתונים',
    text: 'שיתוף והעשרה של מידע: מחירים, קטלוג מוצרים, ברקודים, סניפים ומיקומים. אם יש לכם מידע שמשלים את שלנו, כמו תמונות מוצר, ערכים תזונתיים, כשרות או מיפוי מותגים, או שאתם מחפשים מידע שאנחנו מחזיקים, נשמח לבחון חילופי נתונים.',
  },
  {
    icon: Code,
    title: 'API',
    text: 'גישה תכנותית לנתוני XXL עבור אפליקציות, אתרים ושירותים אחרים. אנחנו בוחנים איך לפתוח אותה בצורה אחראית, ונשמח לשמוע מה הייתם בונים עליה.',
  },
  {
    icon: Bot,
    title: 'MCP ובינה מלאכותית',
    text: 'חיבור עוזרי AI ושירותי סוכנים לנתוני XXL באמצעות Model Context Protocol (MCP), כדי שסוכן יוכל לענות על שאלות כמו "איפה הכי זול היום לקנות את הסל שלי?".',
  },
  {
    icon: Handshake,
    title: 'שותפויות עסקיות ותוכן',
    text: 'רשתות, יצרנים ומותגים, אתרי חיסכון ותוכן, עיתונאים, חוקרים וארגוני צרכנים. הצעות לשילוב, הפניות, מחקר משותף או כל רעיון אחר.',
  },
];

export default function PartnershipsPage() {
  useEffect(() => {
    // applyHostnameMeta() only runs once on app mount, so put the previous
    // values back when leaving this page.
    const descTag = document.querySelector('meta[name="description"]');
    const prevTitle = document.title;
    const prevDesc = descTag?.getAttribute('content') ?? null;
    document.title = TITLE;
    descTag?.setAttribute('content', DESCRIPTION);
    return () => {
      document.title = prevTitle;
      if (prevDesc !== null) descTag?.setAttribute('content', prevDesc);
    };
  }, []);

  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">

      {/* Header strip */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-2 flex items-center justify-between">
          <Link to="/">
            <XxlLogo variant="header" lang="he" className="h-10" />
          </Link>
          <Link to="/" className="text-sm text-emerald-700 hover:underline">
            ← חזרה לדף הבית
          </Link>
        </div>
      </header>

      {/* Body */}
      <main className="max-w-3xl mx-auto px-4 py-10">
        <div className="bg-white rounded-2xl border border-gray-200 p-6 md:p-8">

          <h1 className="text-3xl font-bold text-[#022C22]">שיתופי פעולה</h1>
          <p className="text-lg md:text-xl font-medium text-[#022C22] mt-3 leading-relaxed">
            XXL פתוחה לשיתופי פעולה: נתונים, API, MCP וכל כיוון אחר שיכול לחסוך כסף לצרכנים.
          </p>

          <div className="mt-8 space-y-8 text-gray-700 leading-relaxed">

            <p>
              XXL היא קבוצת אתרים בעברית שנבנתה סביב רעיון אחד: שכל אחד יוכל לקנות חכם. אנחנו משווים
              מחירי סופר בין רשתות, מחפשים טיסות זולות ובונים את הצעד הבא. אנחנו מאמינים שמידע משתפר
              כשעובדים עליו יחד, ומזמינים כל מי שבונה משהו שימושי סביבו, חברות, יזמים, חוקרים ומפתחים,
              ליצור איתנו קשר.
            </p>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-4">על מה אפשר לדבר</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {TOPICS.map(({ icon: Icon, title, text }) => (
                  <div key={title} className="bg-white border border-gray-200 rounded-2xl p-5">
                    <div className="flex items-center gap-2">
                      <Icon size={24} className="text-emerald-700 shrink-0" aria-hidden="true" />
                      <h3 className="text-lg font-semibold text-[#022C22]">{title}</h3>
                    </div>
                    <p className="text-sm text-gray-600 mt-2 leading-relaxed">{text}</p>
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">איך מתחילים</h2>
              <p>
                שלחו לנו אימייל עם שלושה דברים: מי אתם, מה אתם מציעים או מחפשים, ובאיזה שלב אתם
                נמצאים. כל פנייה נבחנת לגופה ואנחנו חוזרים אליכם.
              </p>
              <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2">
                <a
                  href={MAILTO_HREF}
                  className="inline-flex items-center gap-2 bg-emerald-700 text-white font-medium rounded-xl px-5 py-2.5 hover:bg-emerald-800 transition-colors"
                >
                  <Mail size={18} aria-hidden="true" />
                  כתבו לנו
                </a>
                <a href={MAILTO_HREF} className="text-emerald-700 hover:underline" dir="ltr">
                  {CONTACT_EMAIL}
                </a>
              </div>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">מידע אישי</h2>
              <p>
                שיתופי פעולה עם XXL נוגעים למידע על מוצרים, מחירים וסניפים, לא למידע על אנשים. אנחנו
                לא מוכרים ולא מעבירים מידע אישי של משתמשים. פרטים נוספים
                ב<Link to="/privacy" className="text-emerald-700 hover:underline">מדיניות הפרטיות</Link>.
              </p>
            </section>

          </div>

          <div className="mt-10">
            <Link to="/" className="text-sm text-emerald-700 hover:underline">← חזרה לדף הבית</Link>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
}
