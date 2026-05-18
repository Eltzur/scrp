import { useState } from 'react';
import { X } from 'lucide-react';
import { setCookieConsent } from '../utils/analytics';

export default function CookieBanner() {
  // Initialise from localStorage so banner never flickers back after dismissal
  const [visible, setVisible] = useState<boolean>(() => {
    try { return localStorage.getItem('xxl_cookie_consent') === null; }
    catch { return false; }
  });

  if (!visible) return null;

  const handleDismiss = () => {
    setCookieConsent(true);  // X-dismiss counts as implicit consent
    setVisible(false);
  };

  return (
    <div
      className="fixed bottom-0 inset-x-0 z-50 bg-white border-t border-gray-200 shadow-md"
      role="region"
      aria-label="הסכמה לעוגיות"
      dir="rtl"
    >
      <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between gap-4">
        <p className="text-sm text-gray-700">
          נמשיך, אנו משתמשים בעוגיות לשיפור החוויה
        </p>
        <button
          onClick={handleDismiss}
          aria-label="סגור"
          className="shrink-0 p-1 text-gray-400 hover:text-emerald-600 transition-colors rounded"
        >
          <X size={18} />
        </button>
      </div>
    </div>
  );
}
