import { useState, type ReactNode, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import XxlLogo from '../components/XxlLogo';
import Footer from '../components/Footer';
import { supabase } from '../lib/supabase';

interface ComingSoonProps {
  vertical: 'vacation' | 'fashion';
  icon:     ReactNode;
  headline: string;
  subline:  string;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function ComingSoonPage({ vertical, icon, headline, subline }: ComingSoonProps) {
  const [email,    setEmail]    = useState('');
  const [emailErr, setEmailErr] = useState('');
  const [success,  setSuccess]  = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setEmailErr('');
    if (!EMAIL_RE.test(email)) {
      setEmailErr('אימייל לא תקין');
      return;
    }

    const { error } = await supabase
      .from('portal_email_signups')
      .insert({
        email:      email.trim().toLowerCase(),
        vertical,
        user_agent: navigator.userAgent.slice(0, 500),
        referrer:   document.referrer.slice(0, 500) || null,
      });

    if (error) {
      // Log but don't surface to user — show success anyway
      console.error('[ComingSoonPage] Signup error:', error);
    }

    setSuccess(true);
    setEmail('');
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
      <section className="pt-20 pb-8 text-center">
        <div className="flex justify-center">{icon}</div>
        <h1 className="text-3xl md:text-4xl font-bold text-[#022C22] mt-6">{headline}</h1>
        <p className="text-lg text-gray-600 mt-4 max-w-xl mx-auto px-4">{subline}</p>
      </section>

      {/* Email signup */}
      <section className="max-w-md mx-auto mt-12 px-4">
        <div className="bg-white border border-gray-200 rounded-2xl p-6">
          {success ? (
            <p className="text-center font-medium text-emerald-700 py-4">
              תודה! נעדכן אתכם בקרוב 🎉
            </p>
          ) : (
            <form onSubmit={handleSubmit}>
              <p className="font-medium text-[#022C22] mb-3">
                השאירו אימייל ונעדכן אתכם כשנעלה
              </p>
              <input
                type="email"
                value={email}
                onChange={e => { setEmail(e.target.value); setEmailErr(''); }}
                placeholder="your@email.com"
                dir="ltr"
                className="w-full border border-gray-300 rounded-lg p-3 text-left focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
              {emailErr && (
                <p className="text-sm text-red-600 mt-1">{emailErr}</p>
              )}
              <button
                type="submit"
                className="w-full bg-emerald-600 text-white font-medium rounded-lg py-3 mt-3 hover:bg-emerald-700 transition-colors"
              >
                עדכנו אותי כשתעלה
              </button>
              <p className="text-xs text-gray-500 mt-2 text-center">
                לא נשלח ספאם, רק עדכון השקה
              </p>
            </form>
          )}
        </div>
      </section>

      {/* Back link */}
      <div className="mt-8 text-center">
        <Link to="/portal-preview" className="text-sm text-emerald-600 hover:underline">
          ← חזרה לדף הבית
        </Link>
      </div>

      <Footer />
    </div>
  );
}
