import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '../components/AuthContext';
import { AUTH_MSG } from '../lib/authErrors';

/**
 * SU11A-41: password reset by a 6-digit code from the email.
 *   1. email -> resetPasswordForEmail (no redirect URL; the email carries a code)
 *   2. code + new password -> verifyOtp(type 'recovery') -> updateUser
 * The "sent" message is the same whether or not the account exists, and step 2
 * opens either way, so the page never reveals which addresses are registered.
 */
const RESEND_COOLDOWN_S = 60;

const inputClass =
  'w-full px-3 py-2 border border-gray-300 rounded-lg text-sm ' +
  'focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent';

export default function ResetPasswordPage() {
  const { resetPassword, verifyResetCode, updatePassword } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const prefill  = (location.state as { email?: unknown } | null)?.email;

  const [step,     setStep]     = useState<'email' | 'code'>('email');
  const [email,    setEmail]    = useState(typeof prefill === 'string' ? prefill : '');
  const [code,     setCode]     = useState('');
  const [password, setPassword] = useState('');
  const [confirm,  setConfirm]  = useState('');
  const [error,    setError]    = useState<string | null>(null);
  const [notice,   setNotice]   = useState<string | null>(null);
  const [loading,  setLoading]  = useState(false);
  const [cooldown, setCooldown] = useState(0);
  // The code is single-use: after verifyOtp succeeded, a retry following a
  // failed updateUser (e.g. same password as before) must not verify again.
  const verified = useRef(false);

  useEffect(() => {
    document.title = 'איפוס סיסמה | SUPER XXL';
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const id = setTimeout(() => setCooldown(s => s - 1), 1000);
    return () => clearTimeout(id);
  }, [cooldown]);

  const sendCode = async () => {
    if (loading) return;
    setError(null);
    setNotice(null);
    setLoading(true);
    const result = await resetPassword(email);
    setLoading(false);
    if (result.error) {
      setError(result.error);
      return;
    }
    setNotice('אם קיים חשבון עם כתובת זו, נשלח אליו קוד לאיפוס הסיסמה.');
    setStep('code');
    setCooldown(RESEND_COOLDOWN_S);
  };

  const handleSendCode = (e: FormEvent) => {
    e.preventDefault();
    void sendCode();
  };

  const handleReset = async (e: FormEvent) => {
    e.preventDefault();
    if (loading) return;
    setError(null);
    setNotice(null);
    if (!/^\d{6}$/.test(code)) {
      setError(AUTH_MSG.badCode);
      return;
    }
    if (password !== confirm) {
      setError(AUTH_MSG.passwordMismatch);
      return;
    }
    setLoading(true);
    if (!verified.current) {
      const check = await verifyResetCode(email, code);
      if (check.error) {
        setLoading(false);
        setError(check.error);
        return;
      }
      verified.current = true;
    }
    const result = await updatePassword(password);
    setLoading(false);
    if (result.error) {
      setError(result.error);
      return;
    }
    // verifyOtp left a session, so the user is now signed in.
    navigate('/');
    toast.success('הסיסמה עודכנה');
  };

  const submitButton = (idle: string, busy: string) => (
    <button
      type="submit"
      disabled={loading}
      aria-busy={loading}
      className="w-full py-2.5 bg-emerald-700 text-white rounded-xl text-sm font-semibold
                 hover:bg-emerald-800 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
    >
      {loading
        ? <span className="inline-flex items-center justify-center gap-2"><Loader2 size={16} className="animate-spin" aria-hidden="true" />{busy}</span>
        : idle}
    </button>
  );

  const messages = (
    <>
      {error && (
        <p role="alert" className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
          {notice}
        </p>
      )}
    </>
  );

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4" dir="rtl">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
        <h1 className="text-xl font-bold text-gray-900 mb-6 text-center">איפוס סיסמה</h1>

        {step === 'email' ? (
          <form onSubmit={handleSendCode} className="space-y-4">
            <p className="text-sm text-gray-600">נשלח אליכם קוד לאיפוס הסיסמה לכתובת האימייל שהזנתם.</p>
            <div>
              <label htmlFor="reset-email" className="block text-sm font-medium text-gray-700 mb-1">אימייל</label>
              <input
                id="reset-email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className={inputClass}
                dir="ltr"
              />
            </div>
            {messages}
            {submitButton('שליחת קוד', 'שולח…')}
          </form>
        ) : (
          <form onSubmit={handleReset} className="space-y-4">
            <p className="text-sm text-gray-600" dir="ltr" style={{ textAlign: 'right' }}>{email.trim()}</p>
            <div>
              <label htmlFor="reset-code" className="block text-sm font-medium text-gray-700 mb-1">קוד מהאימייל</label>
              <input
                id="reset-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                value={code}
                // Digits only: drops the spaces a pasted "123 456" carries.
                onChange={e => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className={`${inputClass} tracking-widest`}
                dir="ltr"
              />
            </div>
            <div>
              <label htmlFor="reset-password" className="block text-sm font-medium text-gray-700 mb-1">סיסמה חדשה</label>
              <input
                id="reset-password"
                type="password"
                required
                minLength={6}
                autoComplete="new-password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className={inputClass}
                dir="ltr"
              />
            </div>
            <div>
              <label htmlFor="reset-confirm" className="block text-sm font-medium text-gray-700 mb-1">אימות הסיסמה החדשה</label>
              <input
                id="reset-confirm"
                type="password"
                required
                minLength={6}
                autoComplete="new-password"
                value={confirm}
                onChange={e => setConfirm(e.target.value)}
                className={inputClass}
                dir="ltr"
              />
            </div>
            {messages}
            {submitButton('איפוס סיסמה', 'מאפס…')}

            <div className="flex flex-col items-center gap-2 pt-1">
              <button
                type="button"
                onClick={() => void sendCode()}
                disabled={cooldown > 0 || loading}
                className="text-sm font-semibold text-emerald-700 hover:underline
                           disabled:text-gray-400 disabled:no-underline disabled:cursor-not-allowed"
              >
                {cooldown > 0 ? `שליחת קוד חדש בעוד ${cooldown} שניות` : 'שליחת קוד חדש'}
              </button>
              <button
                type="button"
                onClick={() => {
                  verified.current = false;
                  setCode('');
                  setError(null);
                  setNotice(null);
                  setStep('email');
                }}
                disabled={loading}
                className="text-sm text-gray-500 hover:underline"
              >
                שינוי כתובת האימייל
              </button>
            </div>
          </form>
        )}

        <p className="mt-5 text-center text-sm text-gray-500">
          <Link to="/login" className="text-emerald-700 font-semibold hover:text-emerald-700">
            חזרה להתחברות
          </Link>
        </p>
      </div>
    </div>
  );
}
