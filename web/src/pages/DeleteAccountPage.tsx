/**
 * /account/delete — account deletion (SU11A-31; backend SU11A-28, design SU11A-27).
 *
 * PUBLIC on purpose: Google Play requires a deletion URL that works without the
 * app and without signing in, so everything that explains the process renders
 * for signed-out visitors too. The deletion form itself appears only when
 * signed in; signed-out visitors get a link to the existing /login page.
 *
 * Flow: password -> confirm() (the site's existing confirm pattern, as on
 * MyBasketsPage) -> reauthenticate (fresh token; the server refuses tokens older
 * than 5 minutes) -> DELETE /account with that token. On "reauth" the sign-in is
 * repeated once and the call retried once. Deleted (204, or 401 account_deleted)
 * or pending (202): local sign-out, cached data cleared, confirmation shown.
 * The local basket (device-only) is left alone.
 */
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, Trash2 } from 'lucide-react';
import { useAuth } from '../components/AuthContext';
import { deleteAccount, type DeleteAccountResult } from '../api/client';

const MSG = {
  passwordRequired: 'יש להזין סיסמה.',
  wrongPassword: 'הסיסמה שגויה. נסו שוב.',
  offline: 'אין חיבור לאינטרנט או שהשרת אינו זמין. בדקו את החיבור ונסו שוב.',
  protectedAccount:
    'לא ניתן למחוק את החשבון הזה דרך האתר. לבקשת מחיקה כתבו אלינו: info@xxl.co.il',
  failed: 'לא הצלחנו למחוק כרגע, נסו שוב. החשבון נשאר כפי שהיה או שהמחיקה בתהליך.',
  generic: 'משהו השתבש. נסו שוב.',
  confirm: 'למחוק את החשבון לצמיתות?\nלא ניתן לבטל פעולה זו.',
};

type Outcome = 'deleted' | 'pending' | null;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="text-xl font-semibold text-[#022C22] mb-3">{title}</h2>
      {children}
    </section>
  );
}

export default function DeleteAccountPage() {
  const { user, isLoading, reauthenticate, finishAccountDeletion } = useAuth();
  const queryClient = useQueryClient();
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>(null);
  // A ref, not state: two submits inside one render would both see busy=false.
  const inFlight = useRef(false);
  const errorRef = useRef<HTMLDivElement>(null);
  const doneRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    document.title = 'מחיקת חשבון | SUPER XXL';
  }, []);
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error]);
  useEffect(() => {
    if (outcome) doneRef.current?.focus();
  }, [outcome]);

  const run = async () => {
    let result: DeleteAccountResult = { kind: 'reauth' };
    // At most two rounds: the first, and one retry if the server still finds
    // the fresh token too old (clock skew, a very slow network).
    for (let round = 0; round < 2 && result.kind === 'reauth'; round++) {
      const auth = await reauthenticate(password);
      if ('reason' in auth) {
        setError(
          auth.reason === 'invalid_credentials'
            ? MSG.wrongPassword
            : auth.reason === 'network'
              ? MSG.offline
              : MSG.generic,
        );
        return;
      }
      result = await deleteAccount(auth.accessToken);
    }

    if (result.kind === 'deleted' || result.kind === 'pending') {
      await finishAccountDeletion();
      queryClient.clear();
      setPassword('');
      setOutcome(result.kind);
      return;
    }
    if (result.kind === 'protected') setError(MSG.protectedAccount);
    else if (result.kind === 'error' && result.reason !== 'http') setError(MSG.offline);
    else setError(MSG.failed);
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (inFlight.current) return;
    setError(null);
    if (!password) {
      setError(MSG.passwordRequired);
      return;
    }
    if (!window.confirm(MSG.confirm)) return;
    inFlight.current = true;
    setBusy(true);
    try {
      await run();
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  };

  return (
    <main className="max-w-3xl mx-auto px-4 py-10" dir="rtl">
      <div className="bg-white rounded-2xl border border-gray-200 p-6 md:p-8">
        <h1 className="text-3xl font-bold text-[#022C22]">מחיקת חשבון SUPER XXL</h1>
        <p className="mt-3 text-gray-700 leading-relaxed">
          עמוד זה מסביר כיצד למחוק את חשבון המשתמש שלכם בשירות SUPER XXL של XXL בע"מ — האתר
          super.xxl.co.il ואפליקציית SUPER XXL — ומה קורה למידע שלכם לאחר המחיקה.
        </p>

        {/* Warning in words, not only in colour. */}
        <div className="mt-6 flex gap-3 rounded-xl border border-rose-300 bg-rose-50 p-4 text-rose-900">
          <AlertTriangle size={20} className="mt-0.5 shrink-0" aria-hidden="true" />
          <div className="space-y-1">
            <p className="font-bold">חשוב: מחיקת החשבון היא סופית ולא ניתן לבטל אותה.</p>
            <p className="text-sm">
              החשבון משותף לכל שירותי XXL. מחיקתו מסיימת את ההתחברות בכולם, כולל XXL טיסות
              (fly.xxl.co.il).
            </p>
          </div>
        </div>

        <div className="mt-8 space-y-8 text-gray-700 leading-relaxed">
          <Section title="מחיקה באפליקציה">
            <p>
              פתחו את אפליקציית SUPER XXL ← <strong>הגדרות</strong> ← <strong>מחיקת חשבון</strong>,
              הזינו את הסיסמה ואשרו.
            </p>
          </Section>

          <Section title="מחיקה כאן באתר">
            {outcome ? (
              <div role="status" className="rounded-xl border border-emerald-300 bg-emerald-50 p-4">
                <h3 ref={doneRef} tabIndex={-1} className="font-bold text-emerald-900 outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 rounded">
                  החשבון נמחק
                </h3>
                <p className="mt-1 text-emerald-900">
                  {outcome === 'pending'
                    ? 'המידע שלכם נמחק. מחיקת פרטי ההתחברות תושלם תוך 24 שעות.'
                    : 'החשבון והמידע המשויך אליו נמחקו, וההתחברות בדפדפן זה הסתיימה.'}
                </p>
                <Link to="/" className="mt-3 inline-block text-sm text-emerald-700 hover:underline">
                  חזרה לדף הבית
                </Link>
              </div>
            ) : isLoading ? (
              <p aria-live="polite">טוען…</p>
            ) : !user ? (
              <p>
                כדי למחוק את החשבון באתר יש{' '}
                <Link to="/login" className="font-semibold text-emerald-700 hover:underline">
                  להתחבר
                </Link>{' '}
                ולחזור לעמוד זה (תפריט החשבון ← "מחיקת חשבון").
              </p>
            ) : (
              <form onSubmit={onSubmit} className="space-y-4" noValidate>
                <p className="text-sm">
                  מחוברים כ-<span dir="ltr">{user.email}</span>. להמשך הזינו את הסיסמה שלכם.
                </p>
                <div>
                  <label htmlFor="delete-password" className="block text-sm font-medium text-gray-700 mb-1">
                    סיסמה
                  </label>
                  <input
                    id="delete-password"
                    name="password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => {
                      setPassword(e.target.value);
                      if (error) setError(null);
                    }}
                    aria-invalid={error ? true : undefined}
                    aria-describedby={error ? 'delete-error' : undefined}
                    className="w-full max-w-sm px-3 py-2 border border-gray-300 rounded-lg text-sm text-gray-900 bg-white
                               focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
                    dir="ltr"
                  />
                </div>

                <div aria-live="assertive">
                  {error && (
                    <div
                      id="delete-error"
                      ref={errorRef}
                      tabIndex={-1}
                      role="alert"
                      className="text-sm text-rose-700 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2 outline-none
                                 focus-visible:ring-2 focus-visible:ring-rose-500"
                    >
                      {error}
                    </div>
                  )}
                </div>

                <button
                  type="submit"
                  disabled={busy}
                  aria-busy={busy}
                  className="inline-flex min-h-11 items-center gap-2 px-5 py-2.5 bg-rose-700 text-white rounded-xl text-sm font-semibold
                             hover:bg-rose-800 disabled:opacity-60 disabled:cursor-not-allowed transition-colors
                             focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-rose-600"
                >
                  <Trash2 size={16} aria-hidden="true" />
                  {busy ? 'מוחק…' : 'מחיקת החשבון לצמיתות'}
                </button>
              </form>
            )}
          </Section>

          <Section title="מה נמחק">
            <ul className="list-disc pr-6 space-y-1">
              <li>פרטי ההתחברות: כתובת האימייל והסיסמה</li>
              <li>סלי הקניות השמורים</li>
              <li>המוצרים המועדפים</li>
              <li>הדירוגים והביקורות שפרסמתם, כולל אלה שמוצגים לכלל המשתמשים</li>
              <li>התראות וחיפושים שמורים ב-XXL טיסות</li>
            </ul>
            <p className="mt-2">המחיקה מתבצעת מיד, ומחיקת פרטי ההתחברות מסתיימת תוך 24 שעות.</p>
          </Section>

          <Section title="מה נשמר ולכמה זמן">
            <ul className="list-disc pr-6 space-y-1">
              <li>
                דיווחים שהגשתם על תוכן של משתמשים אחרים נשמרים כרשומות בקרה, ללא זיהוי שלכם.
              </li>
              <li>
                רשומה טכנית של בקשת המחיקה (מזהה משתמש בלבד, ללא אימייל) נשמרת רק כדי למנוע שימוש
                חוזר בהתחברות שנמחקה.
              </li>
              <li>
                יומני השרת נמחקים אוטומטית במחזור קבוע: יומני שרת האינטרנט לאחר 14 יום, ויומני
                היישום לאחר 30 יום לכל היותר.
              </li>
              <li>הודעות אימייל תפעוליות נשמרות רק כל עוד הן נחוצות לתפעול ולבקרה.</li>
              <li>
                עותקים של מסד הנתונים בגיבויים נשמרים עד שהם מוחלפים במחזור הגיבוי הרגיל, עד כ-6
                חודשים (180 יום), הן בשרת שלנו והן בעותק הגיבוי החיצוני.
              </li>
              <li>
                הגדרות שנשמרות רק בדפדפן או במכשיר שלכם (למשל סל הקניות המקומי) אינן נשמרות אצלנו ואינן
                נמחקות עם החשבון.
              </li>
            </ul>
          </Section>

          <Section title="אין לכם אפשרות להתחבר?">
            <p>
              שלחו בקשת מחיקה ל-
              <a href="mailto:info@xxl.co.il" className="text-emerald-700 hover:underline">
                info@xxl.co.il
              </a>{' '}
              מכתובת האימייל הרשומה בחשבון. כתובות שנרשמו לעדכונים בדפי "בקרוב" אינן חלק מהחשבון;
              להסרתן פנו אלינו באותה כתובת.
            </p>
          </Section>

          <p className="text-sm">
            לפרטים נוספים ראו את{' '}
            <Link to="/privacy#account-deletion" className="text-emerald-700 hover:underline">
              מדיניות הפרטיות
            </Link>
            .
          </p>
        </div>
      </div>
    </main>
  );
}
