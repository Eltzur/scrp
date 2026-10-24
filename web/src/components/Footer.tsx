import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import AppBadges from './AppBadges';
import { openCookiePreferences } from '../utils/analytics';
import { isPortalHostname } from '../utils/hostname';

export default function Footer() {
  const { t } = useTranslation();
  return (
    <footer className="mt-12 pt-6 border-t border-gray-200 text-center text-sm text-gray-500 pb-6" dir="rtl">
      {/* SU11A-53: the app on every super page (the portal shows it in its SUPER XXL card) */}
      {!isPortalHostname() && (
        <div className="mb-4">
          <p className="text-xs text-gray-600 mb-2">{t('apps.footer_title')}</p>
          <AppBadges size="sm" />
        </div>
      )}
      <p>© XXL {new Date().getFullYear()} · כל הזכויות שמורות</p>
      <p className="mt-2 flex items-center justify-center gap-3 flex-wrap">
        {/* SU11A-40: partnerships link on the portal only (the route works on both hosts). */}
        {isPortalHostname() && (
          <>
            <Link to="/partnerships" className="hover:text-emerald-700 transition-colors">שיתופי פעולה</Link>
            <span className="text-gray-500">|</span>
          </>
        )}
        <Link to="/privacy" className="hover:text-emerald-700 transition-colors">מדיניות פרטיות</Link>
        <span className="text-gray-500">|</span>
        <Link to="/disclaimer" className="hover:text-emerald-700 transition-colors">תנאי שימוש</Link>
        <span className="text-gray-500">|</span>
        <a href="mailto:info@xxl.co.il" className="hover:text-emerald-700 transition-colors">צור קשר</a>
        <span className="text-gray-500">|</span>
        <Link to="/accessibility" className="hover:text-emerald-700 transition-colors">נגישות</Link>
        <span className="text-gray-500">|</span>
        {/* Re-entry to the consent choice from every page, since a declined
            visitor otherwise has no route back to the banner. */}
        <button
          onClick={openCookiePreferences}
          className="hover:text-emerald-700 transition-colors"
        >
          עוגיות
        </button>
      </p>
    </footer>
  );
}
