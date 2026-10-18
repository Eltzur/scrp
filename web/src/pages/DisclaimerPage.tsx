import { useEffect, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import XxlLogo from '../components/XxlLogo';
import Footer from '../components/Footer';
import { LEGAL_ENTITY_NAME, TERMS_DATE, TERMS_VERSION } from '../legal/terms';

// SU11A-44: the full terms of use (route kept at /disclaimer, which the app links
// to). Sections 1-10 follow docs/super/su11a42_ugc_report.md section 6 and say the
// same as the app's terms screen; the earlier disclaimer text (data sources, no
// accuracy warranty, final price set by the seller) is kept in sections 2 and 8.

const TITLE = 'תנאי שימוש | XXL';

const link = 'text-emerald-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 rounded';

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-xl font-semibold text-[#022C22] mb-3">{title}</h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

export default function DisclaimerPage() {
  useEffect(() => {
    // applyHostnameMeta() only runs once on app mount, so put the previous title
    // back when leaving this page.
    // Deferred one tick: on a direct load App's own mount effect (a parent, so
    // it runs after this one) sets the hostname title and would overwrite ours.
    let prevTitle = document.title;
    const id = window.setTimeout(() => {
      prevTitle = document.title;
      document.title = TITLE;
    }, 0);
    return () => {
      window.clearTimeout(id);
      document.title = prevTitle;
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

          <h1 className="text-3xl font-bold text-[#022C22]">תנאי שימוש</h1>
          <p className="text-sm text-gray-600 mt-2">
            גרסה <span dir="ltr">{TERMS_VERSION}</span> · עודכן לאחרונה {TERMS_DATE}
          </p>

          <div className="mt-8 space-y-8 text-gray-700 leading-relaxed">

            <Section title="1. כללי">
              <p>השימוש באפליקציית SUPER XXL ובאתרי XXL ("השירות") כפוף לתנאים אלה ול<Link to="/privacy" className={link}>מדיניות הפרטיות</Link>. הרשמה לשירות או שימוש בו מהווים הסכמה לתנאים. אם אינכם מסכימים להם, אל תשתמשו בשירות.</p>
              <p>השירות מופעל על ידי {LEGAL_ENTITY_NAME}.</p>
            </Section>

            <Section title="2. אופי השירות ומקורות המידע">
              <p>XXL הוא שירות השוואת מחירים המרכז ומציג ("משקף") מידע המתקבל ממקורות צד שלישי. אנו איננו קמעונאי, חברת תעופה, סוכנות נסיעות או מוכר של אף אחד מהמוצרים או השירותים המוצגים בשירות.</p>
              <ul className="list-disc pr-6 space-y-2">
                <li><strong>מחירי מוצרי מזון וסופרמרקטים</strong>: מבוססים על קבצי שקיפות מחירים שקמעונאים מפרסמים באופן יזום בהתאם לחוק שקיפות מחירים, ונטענים אוטומטית מדי יום.</li>
                <li><strong>מחירי טיסות</strong>: מבוססים על נתונים המתקבלים מ-SerpApi, המשקף תוצאות Google Flights.</li>
              </ul>
              <p>המידע מוצג "כפי שהוא" (AS IS). איננו הבעלים של המידע, איננו מאמתים אותו באופן עצמאי, ואיננו יכולים לערוב לדיוקו, לעדכניותו או לזמינותו בכל רגע נתון. מחירים, מבצעים וזמינות מוצרים או טיסות עשויים להשתנות ללא הודעה מוקדמת, ונתונים בשירות עשויים לשקף מצב שאינו עדכני ברגע הצפייה שלכם.</p>
              <p>המחיר, הזמינות ותנאי הרכישה הסופיים נקבעים אך ורק על ידי הקמעונאי, הרשת או חברת התעופה הרלוונטית בעת ביצוע הרכישה בפועל, באתר שלהם או בסניף שלהם.</p>
            </Section>

            <Section title="3. חשבון משתמש">
              <p>אתם אחראים לשמירת הסיסמה שלכם ולכל פעולה שנעשית בחשבון. אפשר למחוק את החשבון בכל עת: באפליקציה בהגדרות › מחיקת חשבון, ובאתר בעמוד <Link to="/account/delete" className={link}>מחיקת חשבון</Link>.</p>
            </Section>

            <Section title="4. תוכן שאתם מפרסמים">
              <p>דירוגים וביקורות שאתם מפרסמים מוצגים לכל משתמשי השירות, בלי שמכם ובלי כתובת האימייל שלכם. אתם אחראים לתוכן שאתם מפרסמים, ובפרסומו אתם מרשים ל-XXL להציג אותו בשירות.</p>
            </Section>

            <Section title="5. אפס סובלנות לתוכן פוגעני ולמשתמשים פוגעניים">
              <p>אסור לפרסם תוכן פוגעני, מעליב, מאיים, מטריד, גזעני, מיני, אלים, משמיץ, מפר זכויות או בלתי חוקי, וגם לא פרסומות, ספאם או פרטים אישיים של אחרים. אין לנו שום סבלנות לתוכן כזה או למשתמשים שמפרסמים אותו: התוכן יוסר, והחשבון עלול להיחסם או להימחק, גם ללא הודעה מוקדמת.</p>
            </Section>

            <Section title="6. דיווח וחסימה">
              <p>ליד כל ביקורת אפשר לדווח עליה ולחסום את מי שכתב אותה. ביקורות של משתמש שחסמתם לא יוצגו לכם יותר. את רשימת המשתמשים שחסמתם ואת ביטול החסימה מוצאים באפליקציה, בהגדרות › משתמשים חסומים. אנחנו בודקים כל דיווח תוך 24 שעות, מסירים תוכן שמפר את התנאים ונוקטים צעדים נגד מי שפרסם אותו.</p>
            </Section>

            <Section title="7. הפסקת שימוש וסגירת חשבון">
              <p>אנחנו רשאים להסיר תוכן, להגביל חשבון, להשעות אותו או לסגור אותו אם לדעתנו הופרו תנאים אלה.</p>
            </Section>

            <Section title="8. הגבלת אחריות">
              <p>במידה המרבית המותרת לפי דין, XXL לא תישא באחריות לנזק ישיר או עקיף, לרבות אך לא רק אובדן רכישה משתלמת, שנגרם מהסתמכות על המידע בשירות או מתוכן שפרסמו משתמשים אחרים.</p>
              <p>XXL אינה צד לעסקה שתבצעו מול צד שלישי, ואינה אחראית לכל פער בין המידע שהוצג בשירות לבין המחיר או הזמינות בפועל אצל הספק.</p>
            </Section>

            <Section title="9. שינויים בתנאים">
              <p>אנחנו עשויים לעדכן תנאים אלה מעת לעת. על שינוי מהותי נודיע בשירות, וייתכן שנבקש מכם לאשר את התנאים מחדש. המשך השימוש בשירות לאחר עדכון מהווה הסכמה לתנאים המעודכנים.</p>
            </Section>

            <Section title="10. יצירת קשר">
              <p>לשאלות, לדיווח על תוכן או על משתמש: <a href="mailto:info@xxl.co.il" className={link}>info@xxl.co.il</a></p>
              <p><Link to="/privacy" className={link}>מדיניות הפרטיות</Link></p>
            </Section>

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
