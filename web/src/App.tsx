import { lazy, Suspense, useEffect, useState } from 'react';
import { Routes, Route, useLocation } from 'react-router-dom';
import { Toaster } from 'sonner';
import { BasketProvider } from './components/BasketContext';
import { FavoritesProvider } from './components/FavoritesContext';
import BasketDrawer from './components/BasketDrawer';
import Header from './components/Header';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import MyBasketsPage from './pages/MyBasketsPage';
import FavoritesPage from './pages/FavoritesPage';
import MyRatingsPage from './pages/MyRatingsPage';
import PromosPage from './pages/PromosPage';
// Portal routes — rendered without the supermarket app shell
import PortalPage from './pages/PortalPage';
import Footer from './components/Footer';
// Rarely visited pages load on demand (SU11A-46) to keep the main chunk small.
const DeleteAccountPage = lazy(() => import('./pages/DeleteAccountPage'));
const ResetPasswordPage = lazy(() => import('./pages/ResetPasswordPage'));
const FashionPage       = lazy(() => import('./pages/FashionPage'));
const PrivacyPolicyPage = lazy(() => import('./pages/PrivacyPolicyPage'));
const DisclaimerPage    = lazy(() => import('./pages/DisclaimerPage'));
const AccessibilityPage = lazy(() => import('./pages/AccessibilityPage'));
const PartnershipsPage  = lazy(() => import('./pages/PartnershipsPage'));
// Utilities
import { getCities } from './api/client';
import type { CityInfo } from './api/client';
import { isPortalHostname } from './utils/hostname';
import { applyRouteMeta } from './utils/seoMeta';
import { initGA, trackPageview } from './utils/analytics';
import CookieBanner from './components/CookieBanner';
import ExpiredLinkNotice from './components/ExpiredLinkNotice';

// Supermarket app shell — all existing routes are unchanged inside here
function AppShell() {
  const [cities, setCities] = useState<CityInfo[]>([]);

  useEffect(() => {
    getCities().then(setCities);
    fetch('https://api-super.xxl.co.il/health', { method: 'GET' }).catch(() => {});
  }, []);

  return (
    <BasketProvider>
      <FavoritesProvider>
        <Toaster position="top-center" duration={4000} dir="rtl" />
        <BasketDrawer />
        <Header />
        <Suspense fallback={<div className="min-h-screen" />}>
        <Routes>
          <Route path="/"          element={<HomePage cities={cities} />} />
          <Route path="/login"     element={<LoginPage />} />
          <Route path="/signup"    element={<SignupPage />} />
          {/* SU11A-41: password reset by a 6-digit email code. */}
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/baskets"   element={<MyBasketsPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/my-ratings" element={<MyRatingsPage />} />
          <Route path="/promos"    element={<PromosPage />} />
          {/* SU11A-31: public deletion URL (Google Play); the form needs sign-in. */}
          <Route path="/account/delete" element={<DeleteAccountPage />} />
        </Routes>
        </Suspense>
        <Footer />
      </FavoritesProvider>
    </BasketProvider>
  );
}

export default function App() {
  const location = useLocation();

  useEffect(() => {
    initGA();
  }, []);

  // Title, description, canonical, OG and robots for every route (SU11A-46).
  // This parent effect runs after the pages' own effects, so it always wins.
  useEffect(() => {
    applyRouteMeta(location.pathname);
  }, [location.pathname]);

  // Track SPA route changes (GA4 pageview per navigation).
  // Depends on `search` as well as `pathname`: the search page keeps its query
  // in the query string, so /search?q=X -> /search?q=Y is a real navigation the
  // user made, and pathname alone would report it as no movement at all.
  useEffect(() => {
    trackPageview(location.pathname + location.search);
  }, [location.pathname, location.search]);

  return (
    <>
      <CookieBanner />
      <ExpiredLinkNotice />
      <Suspense fallback={<div className="min-h-screen" />}>
      <Routes>
        {/* Portal routes — standalone, no supermarket header/basket/auth providers */}
        <Route path="/portal-preview" element={<PortalPage />} />
        <Route path="/fashion"        element={<FashionPage />} />
        {/* Legal pages — standalone portal-style pages (own header strip + Footer),
            registered here rather than inside AppShell so they don't inherit the
            supermarket Header/BasketDrawer chrome. Absolute paths rank above the
            "/*" catch-all, so they resolve on both super.xxl.co.il and the portal. */}
        <Route path="/privacy"        element={<PrivacyPolicyPage />} />
        <Route path="/disclaimer"     element={<DisclaimerPage />} />
        <Route path="/accessibility"  element={<AccessibilityPage />} />
        {/* SU11A-40: works on both hosts; the footer links to it on the portal only. */}
        <Route path="/partnerships"   element={<PartnershipsPage />} />
        {/* On portal hostnames (xxl.co.il, www.xxl.co.il, localhost?portal=1),
            "/" renders PortalPage. On super.xxl.co.il this Route is absent,
            so "/" falls through to the "/*" catch-all → AppShell. */}
        {isPortalHostname() ? (
          <Route path="/" element={<PortalPage />} />
        ) : null}
        {/* All existing supermarket app routes — untouched */}
        <Route path="/*" element={<AppShell />} />
      </Routes>
      </Suspense>
    </>
  );
}
