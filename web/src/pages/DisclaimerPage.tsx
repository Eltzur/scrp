import { Link } from 'react-router-dom';
import XxlLogo from '../components/XxlLogo';
import Footer from '../components/Footer';

export default function DisclaimerPage() {
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

          <h1 className="text-3xl font-bold text-[#022C22]">תנאי שימוש וכתב ויתור אחריות</h1>
          <p className="text-sm text-gray-500 mt-2">עודכן לאחרונה: 12 ביולי 2026</p>

          <div className="mt-8 space-y-8 text-gray-700 leading-relaxed">

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">1. אופי השירות</h2>
              <p>XXL הוא שירות השוואת מחירים המרכז ומציג ("משקף") מידע המתקבל ממקורות צד שלישי. אנו איננו קמעונאי, חברת תעופה, סוכנות נסיעות או מוכר של אף אחד מהמוצרים או השירותים המוצגים באתר.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">2. מקורות המידע</h2>
              <ul className="list-disc pr-6 mt-3 space-y-2">
                <li><strong>מחירי מוצרי מזון וסופרמרקטים</strong>: מבוססים על קבצי שקיפות מחירים שקמעונאים מפרסמים באופן יזום בהתאם לחוק שקיפות מחירים, ונטענים אוטומטית מדי יום.</li>
                <li><strong>מחירי טיסות</strong>: מבוססים על נתונים המתקבלים מ-SerpApi, המשקף תוצאות Google Flights.</li>
              </ul>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">3. אין אחריות לדיוק המידע</h2>
              <p>המידע המוצג באתר מוצג "כפי שהוא" (AS IS). איננו הבעלים של המידע, איננו מאמתים אותו באופן עצמאי, ואיננו יכולים לערוב לדיוקו, לעדכניותו או לזמינותו בכל רגע נתון. מחירים, מבצעים וזמינות מוצרים או טיסות עשויים להשתנות ללא הודעה מוקדמת, ונתונים באתר עשויים לשקף מצב שאינו עדכני ברגע הצפייה שלכם.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">4. המחיר הסופי נקבע על ידי הספק</h2>
              <p>המחיר, הזמינות ותנאי הרכישה הסופיים ייקבעו אך ורק על ידי הקמעונאי, הרשת או חברת התעופה הרלוונטית בעת ביצוע הרכישה בפועל באתר שלהם או בסניף שלהם. XXL אינה צד לעסקה שתבצעו מול צד שלישי, ואינה אחראית לכל פער בין המידע שהוצג באתרנו לבין המחיר או הזמינות בפועל אצל הספק.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">5. הגבלת אחריות</h2>
              <p>במידה המרבית המותרת על פי דין, XXL לא תישא באחריות לכל נזק ישיר או עקיף, לרבות אך לא רק אובדן רכישה משתלמת, הנובע מהסתמכות על המידע המוצג בשירות.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">6. שינויים בתנאים</h2>
              <p>אנו עשויים לעדכן תנאים אלו מעת לעת. המשך השימוש בשירות לאחר עדכון מהווה הסכמה לתנאים המעודכנים.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">7. יצירת קשר</h2>
              <p>שאלות בנוגע לתנאים אלו: <a href="mailto:info@xxl.co.il" className="text-emerald-600 hover:underline">info@xxl.co.il</a>.</p>
            </section>

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
