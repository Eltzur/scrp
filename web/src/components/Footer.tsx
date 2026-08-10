import { Link } from 'react-router-dom';
import { openCookiePreferences } from '../utils/analytics';

export default function Footer() {
  return (
    <footer className="mt-12 pt-6 border-t border-gray-200 text-center text-sm text-gray-500 pb-6" dir="rtl">
      <p>© XXL {new Date().getFullYear()} · כל הזכויות שמורות</p>
      <p className="mt-2 flex items-center justify-center gap-3 flex-wrap">
        <Link to="/privacy" className="hover:text-emerald-600 transition-colors">מדיניות פרטיות</Link>
        <span className="text-gray-300">|</span>
        <Link to="/disclaimer" className="hover:text-emerald-600 transition-colors">תנאי שימוש וכתב ויתור</Link>
        <span className="text-gray-300">|</span>
        <a href="mailto:info@xxl.co.il" className="hover:text-emerald-600 transition-colors">צור קשר</a>
        <span className="text-gray-300">|</span>
        <Link to="/accessibility" className="hover:text-emerald-600 transition-colors">נגישות</Link>
        <span className="text-gray-300">|</span>
        {/* Re-entry to the consent choice from every page, since a declined
            visitor otherwise has no route back to the banner. */}
        <button
          onClick={openCookiePreferences}
          className="hover:text-emerald-600 transition-colors"
        >
          עוגיות
        </button>
      </p>
    </footer>
  );
}
