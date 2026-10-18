import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * SU11A-41: old reset emails carried a one-time link that mail scanners often
 * used up first, landing people on "#error=access_denied&error_code=otp_expired".
 * Explain that and point to the code-based reset; then clear the hash so a
 * reload does not show it again. Any other hash is left alone.
 */
function hasExpiredLinkHash(): boolean {
  try {
    const hash = window.location.hash.replace(/^#/, '');
    if (!hash) return false;
    return new URLSearchParams(hash).get('error_code') === 'otp_expired';
  } catch {
    return false;
  }
}

export default function ExpiredLinkNotice() {
  const navigate = useNavigate();
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!hasExpiredLinkHash()) return;
    setShow(true);
    try {
      window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search);
    } catch {
      // Clearing the hash is cosmetic; the notice still shows.
    }
  }, []);

  if (!show) return null;

  return (
    <div
      role="alert"
      dir="rtl"
      className="fixed top-3 inset-x-3 z-50 mx-auto max-w-md bg-white border border-amber-300 rounded-2xl shadow-lg p-4"
    >
      <p className="text-sm text-gray-800">הקישור אינו תקף יותר. בקשו קוד חדש.</p>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={() => { setShow(false); navigate('/reset-password'); }}
          className="px-4 py-2 bg-emerald-700 text-white rounded-xl text-sm font-semibold hover:bg-emerald-800 transition-colors"
        >
          איפוס סיסמה
        </button>
        <button
          onClick={() => setShow(false)}
          className="text-sm text-gray-500 hover:underline"
        >
          סגירה
        </button>
      </div>
    </div>
  );
}
