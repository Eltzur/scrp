import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../components/AuthContext';

export default function SignupPage() {
  const { signUp }  = useAuth();
  const navigate    = useNavigate();
  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [error,    setError]    = useState<string | null>(null);
  const [loading,  setLoading]  = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const result = await signUp(email, password);
    setLoading(false);
    if (result.error) {
      setError(result.error);
    } else {
      navigate('/');
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4" dir="rtl">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
        <h1 className="text-xl font-bold text-gray-900 mb-6 text-center">להרשמה</h1>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">אימייל</label>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                         focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              dir="ltr"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">סיסמה</label>
            <input
              type="password"
              required
              minLength={6}
              value={password}
              onChange={e => setPassword(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm
                         focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
              dir="ltr"
            />
          </div>

          {error && (
            <p className="text-sm text-rose-600 bg-rose-50 border border-rose-200 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-emerald-700 text-white rounded-xl text-sm font-semibold
                       hover:bg-emerald-800 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'נרשם…' : 'להרשמה'}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-gray-500">
          כבר יש לך חשבון?{' '}
          <Link to="/login" className="text-emerald-700 font-semibold hover:text-emerald-700">
            להתחברות
          </Link>
        </p>
      </div>
    </div>
  );
}
