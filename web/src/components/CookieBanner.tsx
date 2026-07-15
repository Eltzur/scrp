import { useState } from 'react';
import { setCookieConsent } from '../utils/analytics';

export default function CookieBanner() {
  const [visible, setVisible] = useState<boolean>(() => {
    try { return localStorage.getItem('xxl_cookie_consent') === null; }
    catch { return false; }
  });

  if (!visible) return null;

  const handleAccept = () => {
    setCookieConsent(true);
    setVisible(false);
  };

  const handleReject = () => {
    setCookieConsent(false);
    setVisible(false);
  };

  return (
    <div
      className="fixed bottom-0 inset-x-0 z-50 bg-white border-t border-gray-200 shadow-md"
      role="region"
      aria-label="הסכמה לעוגיות"
      dir="rtl"
    >
      <div className="max-w-6xl mx-auto px-4 py-3 flex flex-col sm:flex-row items-center justify-between gap-3">
        <p className="text-sm text-gray-700">
          אנו משתמשים בעוגיות ניתוח (Google Analytics) כדי לשפר את השירות. עוגיות אלו יופעלו רק באישורכם.{' '}
          <a href="/privacy#cookies" className="text-emerald-600 hover:underline">מידע נוסף</a>
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleReject}
            className="px-3 py-1.5 text-sm font-medium text-gray-600 hover:text-gray-800 transition-colors"
          >
            דחייה
          </button>
          <button
            onClick={handleAccept}
            className="px-4 py-1.5 text-sm font-medium text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg transition-colors"
          >
            אישור
          </button>
        </div>
      </div>
    </div>
  );
}
