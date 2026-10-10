import { Link } from 'react-router-dom';
import { Cookie } from 'lucide-react';
import XxlLogo from '../components/XxlLogo';
import Footer from '../components/Footer';
import { openCookiePreferences } from '../utils/analytics';

export default function PrivacyPolicyPage() {
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

          <h1 className="text-3xl font-bold text-[#022C22]">מדיניות פרטיות</h1>
          <p className="text-sm text-gray-500 mt-2">עודכן לאחרונה: 10 באוקטובר 2026</p>

          <div className="mt-8 space-y-8 text-gray-700 leading-relaxed">

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">1. כללי</h2>
              <p>מדיניות זו מפרטת כיצד XXL בע"מ ("XXL", "אנחנו") אוספת, משתמשת ומגנה על מידע אישי של משתמשי האתר xxl.co.il ואתרי המשנה שלו (לרבות super.xxl.co.il ו-fly.xxl.co.il, "השירות"). שימוש בשירות מהווה הסכמה למדיניות זו.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">2. איזה מידע אנו אוספים</h2>
              <p>אנו אוספים מידע בכמה אופנים, בהתאם לאופן שבו אתם משתמשים בשירות:</p>
              <ul className="list-disc pr-6 mt-3 space-y-2">
                <li><strong>הרשמה לעדכונים</strong>: כאשר אתם משאירים כתובת אימייל בדף "בקרוב" (למשל אופנה או חופשות), אנו שומרים את כתובת האימייל, הוורטיקל שבו נרשמתם, וכן פרטים טכניים בסיסיים (סוג דפדפן, עמוד ההפניה) לצורך מניעת הרשמות זדוניות.</li>
                <li><strong>חשבון משתמש</strong>: בעת הרשמה לחשבון, אנו שומרים את כתובת האימייל שלכם וסיסמה מוצפנת (מנוהל דרך ספק האימות שלנו, Supabase). לאחר התחברות אנו עשויים לשמור מוצרים מועדפים וסלי קניות שמורים המקושרים לחשבון שלכם.</li>
                <li><strong>עוגיות וכלי ניתוח</strong>: בכפוף להסכמתכם בבאנר העוגיות, אנו משתמשים ב-Google Analytics כדי להבין כיצד משתמשים בשירות (ראו סעיף 5).</li>
                <li><strong>לוגים טכניים</strong>: כמו כל שירות אינטרנט, שרתי האתר שומרים באופן שגרתי כתובת IP, סוג דפדפן וכתובות שנצפו, למטרות אבטחה ותפעול.</li>
              </ul>
              <p className="mt-4"><strong>מידע שנאסוף בעתיד, עם השקת שירותים נוספים (עדיין לא פעיל):</strong></p>
              <p className="mt-2">ככל שנשיק בעתיד יכולות נוספות כגון רכישות, הזמנות או שירותים בתשלום, אנו צפויים לאסוף גם: שם מלא, מספר טלפון, מספר תעודת זהות, וכתובת מגורים — לצורך זיהוי, יצירת קשר, משלוח וחיוב. <strong>פרטי כרטיס אשראי אינם ואף פעם לא יישמרו על שרתי XXL</strong> — סליקת תשלומים בכרטיס אשראי תתבצע אך ורק דרך ספק סליקה חיצוני מוסמך PCI-DSS, שיקבל את פרטי הכרטיס ישירות; XXL תקבל אישור עסקה בלבד. תשלומים דרך Bit או Paybox מתבצעים ישירות באפליקציות אלו ואינם חושפים ל-XXL פרטי אמצעי תשלום.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">3. למה אנחנו משתמשים במידע</h2>
              <p>לצורך: תפעול השירות ומתן התכונות שביקשתם (למשל שמירת סל קניות); יצירת קשר בנוגע לעדכונים שנרשמתם אליהם; שיפור השירות על בסיס ניתוח שימוש מצטבר; מניעת הונאות ואבטחת המערכת; עמידה בחובות חוקיות; ובעתיד — עיבוד הזמנות ותשלומים.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">4. עם מי אנו חולקים מידע</h2>
              <p>אנו לא מוכרים מידע אישי. אנו משתפים מידע עם ספקי שירות הפועלים מטעמנו בלבד:</p>
              <ul className="list-disc pr-6 mt-3 space-y-2">
                <li><strong>Supabase</strong> — ניהול חשבונות משתמשים ואחסון נתונים.</li>
                <li><strong>Google Analytics (Google Ireland Ltd.)</strong> — ניתוח שימוש אנונימי, בכפוף להסכמתכם לעוגיות.</li>
                <li><strong>ספק סליקת תשלומים חיצוני מוסמך PCI-DSS</strong> (ייבחר לפני השקת תשלומים) — לעיבוד תשלומים בלבד.</li>
                <li>מידע על מחירי טיסות מגיע מ-SerpApi/Google Flights, ומידע על מחירי סופרמרקטים מגיע מקבצי שקיפות מחירים של משרד הכלכלה — אלו מקורות מידע חד-כיווניים; אנו לא שולחים אליהם מידע אישי שלכם.</li>
              </ul>
              <p className="mt-3">נגלה מידע אישי לרשויות אכיפת חוק רק אם נדרש בהליך חוקי.</p>
            </section>

            <section id="cookies">
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">5. עוגיות</h2>
              <p>העוגיות מסייעות לנו להפעיל את האתר ולהבין את השימוש בו. עוגיות חיוניות לתפעול האתר פועלות תמיד. עוגיות ניתוח (Google Analytics) פועלות רק לאחר שתאשרו זאת בבאנר העוגיות המוצג בכניסתכם הראשונה לאתר. תוכלו לשנות את בחירתכם בכל עת:</p>
              <button
                onClick={openCookiePreferences}
                className="mt-3 inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-emerald-600
                           text-sm font-medium text-emerald-700 hover:bg-emerald-50 transition-colors"
              >
                <Cookie size={15} />
                נהל העדפות עוגיות
              </button>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">6. אבטחת מידע</h2>
              <p>אנו נוקטים באמצעים טכניים וארגוניים סבירים להגנה על המידע שלכם, לרבות הצפנת תעבורה (HTTPS/SSL) והגבלת גישה לנתונים לעובדים מורשים בלבד. גיבויי מסד הנתונים בשרת שלנו נשמרים בתיקייה שהגישה אליה מוגבלת לחשבון המערכת של מסד הנתונים ולמנהלי השרת. ככל שתחול עלינו חובת מינוי ממונה הגנת מידע לפי תיקון 13 לחוק הגנת הפרטיות, פרטי הממונה יפורסמו כאן.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">7. הזכויות שלכם</h2>
              <p>בהתאם לחוק הגנת הפרטיות, זכותכם לעיין במידע שנשמר עליכם, לבקש תיקון או מחיקה שלו, ולהתנגד לשימושים מסוימים בו. לצורך מימוש זכויות אלו, פנו אלינו לפי הפרטים בסעיף 10. למחיקת החשבון ראו סעיף 8.</p>
            </section>

            <section id="account-deletion">
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">8. שמירת מידע ומחיקת חשבון</h2>
              <p>אנו שומרים מידע אישי רק לפרק הזמן הדרוש למטרות שלשמן נאסף, או כנדרש בחוק.</p>

              <p className="mt-4"><strong>מחיקת חשבון.</strong> תוכלו למחוק את חשבונכם בכל עת, באחת מהדרכים הבאות:</p>
              <ul className="list-disc pr-6 mt-2 space-y-2">
                <li>באפליקציית SUPER XXL: הגדרות ← "מחיקת חשבון".</li>
                <li>באתר, בעמוד <Link to="/account/delete" className="text-emerald-700 hover:underline">super.xxl.co.il/account/delete</Link> (לאחר התחברות).</li>
                <li>אם אינכם יכולים להתחבר: בפנייה באימייל ל-<a href="mailto:info@xxl.co.il" className="text-emerald-700 hover:underline">info@xxl.co.il</a> מכתובת האימייל הרשומה בחשבון.</li>
              </ul>
              <p className="mt-3">החשבון משותף לכל שירותי XXL (לרבות super.xxl.co.il ו-fly.xxl.co.il). מחיקתו מסיימת את ההתחברות בכל השירותים, כולל XXL טיסות.</p>

              <p className="mt-4"><strong>מה נמחק.</strong> עם המחיקה נמחקים מיד: פרטי ההתחברות (כתובת האימייל והסיסמה המוצפנת), סלי הקניות השמורים, המוצרים המועדפים, הדירוגים והביקורות שפרסמתם (כולל אלה שמוצגים לכלל המשתמשים), והתראות וחיפושים שמורים ב-XXL טיסות. מחיקת החשבון מסתיימת תוך 24 שעות.</p>

              <p className="mt-4"><strong>מה נשמר ולכמה זמן.</strong></p>
              <ul className="list-disc pr-6 mt-2 space-y-2">
                <li>דיווחים שהגשתם על תוכן של משתמשים אחרים נשמרים כרשומות בקרה, ללא זיהוי שלכם.</li>
                <li>רשומה טכנית של בקשת המחיקה (מזהה משתמש בלבד, ללא אימייל) נשמרת רק כדי למנוע שימוש חוזר בהתחברות שנמחקה.</li>
                <li>יומני השרת נמחקים אוטומטית במחזור קבוע: יומני שרת האינטרנט לאחר 14 יום, ויומני היישום לאחר 30 יום לכל היותר.</li>
                <li>הודעות אימייל תפעוליות (למשל התראה על תוכן שהועבר לבדיקה) נשמרות רק כל עוד הן נחוצות לתפעול ולבקרה.</li>
                <li>עותקים של מסד הנתונים בגיבויים נשמרים עד שהם מוחלפים במחזור הגיבוי הרגיל, עד כ-6 חודשים (180 יום), הן בשרת שלנו והן בעותק הגיבוי החיצוני.</li>
              </ul>

              <p className="mt-4"><strong>הרשמה לעדכונים.</strong> כתובות אימייל שנרשמו לעדכונים בדפי "בקרוב" אינן חלק מהחשבון ואינן נמחקות עם מחיקתו. להסרתן פנו אלינו ל-<a href="mailto:info@xxl.co.il" className="text-emerald-700 hover:underline">info@xxl.co.il</a>.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">9. העברת מידע לחו"ל</h2>
              <p>חלק מספקי השירות שלנו (כגון Google ו-Supabase) עשויים לעבד מידע מחוץ לישראל. אנו דואגים שהעברות אלו יתבצעו בכפוף להסכמים ואמצעי הגנה מתאימים.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">10. יצירת קשר</h2>
              <p>לשאלות בנוגע למדיניות זו או למימוש זכויותיכם, ניתן לפנות אלינו בכתובת <a href="mailto:info@xxl.co.il" className="text-emerald-700 hover:underline">info@xxl.co.il</a>.</p>
            </section>

            <section>
              <h2 className="text-xl font-semibold text-[#022C22] mb-3">11. עדכונים למדיניות</h2>
              <p>אנו עשויים לעדכן מדיניות זו מעת לעת. שינויים מהותיים יצוינו בתאריך העדכון בראש העמוד.</p>
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
