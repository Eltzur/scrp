import { lazy, Suspense, useEffect, useState, type ComponentType, type LazyExoticComponent } from 'react';
import { LogOut, ShieldCheck } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Toaster } from 'sonner';
import { useAuth } from '../components/AuthContext';
import { GateScreen, useAdminGate } from './AdminAuth';
import { Loading } from './ui';

/**
 * The admin console (SU11A-54), phase 1. App.tsx renders ONLY this on
 * admin.xxl.co.il (or localhost?admin=1), loaded lazily: the shop's visitors
 * never download it. Hebrew RTL, mobile first.
 *
 * Nothing here edits secrets, runs commands or reaches the database: every
 * action is an API call that the server checks for admin + 2FA.
 *
 * The screen is kept in the URL hash (#queue …), not in the path, so the dev
 * flag ?admin=1 survives navigation and reloads.
 */
const StatusScreen = lazy(() => import('./screens/StatusScreen'));
const QueueScreen = lazy(() => import('./screens/QueueScreen'));
const HistoryScreen = lazy(() => import('./screens/HistoryScreen'));
const AuditScreen = lazy(() => import('./screens/AuditScreen'));

const TABS = ['status', 'queue', 'history', 'audit'] as const;
type Tab = typeof TABS[number];
const SCREENS: Record<Tab, LazyExoticComponent<ComponentType>> = {
  status: StatusScreen, queue: QueueScreen, history: HistoryScreen, audit: AuditScreen,
};

function tabFromHash(): Tab {
  const h = window.location.hash.replace('#', '');
  return (TABS as readonly string[]).includes(h) ? (h as Tab) : 'status';
}

/** XXL Admin title, noindex, and none of the shop's canonical / OG / app tags. */
function useAdminHead() {
  useEffect(() => {
    document.title = 'XXL Admin';
    const head = document.head;
    head.querySelectorAll(
      'link[rel="canonical"], meta[property^="og:"], meta[name^="twitter:"], meta[name="description"], ' +
      'meta[name="keywords"], meta[name="google-play-app"], script#ld-app',
    ).forEach(el => el.remove());
    let robots = head.querySelector<HTMLMetaElement>('meta[name="robots"]');
    if (!robots) {
      robots = document.createElement('meta');
      robots.name = 'robots';
      head.appendChild(robots);
    }
    robots.content = 'noindex,nofollow';
  }, []);
}

function Shell() {
  const { t } = useTranslation();
  const { signOut } = useAuth();
  const [tab, setTab] = useState<Tab>(tabFromHash);

  useEffect(() => {
    const onHash = () => setTab(tabFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  const go = (next: Tab) => {
    setTab(next);
    // replaceState keeps the path and the query (?admin=1 in dev).
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${next}`);
  };
  const Screen = SCREENS[tab];

  return (
    <div className="min-h-screen bg-gray-50" dir="rtl">
      <Toaster position="top-center" duration={4000} dir="rtl" />
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-4 min-h-[56px] flex items-center justify-between gap-3">
          <p className="flex items-center gap-2 font-bold text-gray-900">
            <ShieldCheck size={20} className="text-emerald-700" aria-hidden="true" /> XXL Admin
          </p>
          <button
            type="button"
            onClick={() => void signOut()}
            className="min-h-[44px] px-3 rounded-xl text-sm font-semibold text-gray-800 inline-flex items-center gap-2
              hover:bg-gray-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700"
          >
            <LogOut size={16} aria-hidden="true" /> {t('admin.auth.sign_out')}
          </button>
        </div>
        <nav aria-label={t('admin.nav.label')} className="max-w-5xl mx-auto px-2 overflow-x-auto">
          <ul className="flex gap-1 min-w-max">
            {TABS.map(id => (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => go(id)}
                  aria-current={tab === id ? 'page' : undefined}
                  className={`min-h-[48px] px-3 text-sm font-semibold border-b-2
                    focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-emerald-700
                    ${tab === id ? 'border-emerald-700 text-emerald-800' : 'border-transparent text-gray-700 hover:text-gray-900'}`}
                >
                  {t(`admin.nav.${id}`)}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <main className="max-w-5xl mx-auto px-4 py-5">
        <h1 className="text-xl font-bold text-gray-900 mb-4">{t(`admin.${tab}.title`)}</h1>
        <Suspense fallback={<Loading />}>
          <Screen />
        </Suspense>
        <p className="mt-10 text-xs text-gray-500">{t('admin.nav.soon')}</p>
      </main>
    </div>
  );
}

export default function AdminApp() {
  useAdminHead();
  const { phase, recheck } = useAdminGate();
  if (phase.kind !== 'ready') return <GateScreen phase={phase} recheck={recheck} />;
  return <Shell />;
}
