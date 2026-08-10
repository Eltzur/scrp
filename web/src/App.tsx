import { useEffect, useState } from 'react';
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
import PromosPage from './pages/PromosPage';
// Portal routes — rendered without the supermarket app shell
import PortalPage from './pages/PortalPage';
import FashionPage from './pages/FashionPage';
import PrivacyPolicyPage from './pages/PrivacyPolicyPage';
import DisclaimerPage from './pages/DisclaimerPage';
import AccessibilityPage from './pages/AccessibilityPage';
import Footer from './components/Footer';
// Utilities
import { getCities } from './api/client';
import type { CityInfo } from './api/client';
import { isPortalHostname } from './utils/hostname';
import { applyHostnameMeta } from './utils/seoMeta';
import { initGA, trackPageview } from './utils/analytics';
import CookieBanner from './components/CookieBanner';

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
        <Routes>
          <Route path="/"          element={<HomePage cities={cities} />} />
          <Route path="/login"     element={<LoginPage />} />
          <Route path="/signup"    element={<SignupPage />} />
          <Route path="/baskets"   element={<MyBasketsPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
          <Route path="/promos"    element={<PromosPage />} />
        </Routes>
        <Footer />
      </FavoritesProvider>
    </BasketProvider>
  );
}

export default function App() {
  const location = useLocation();

  // Apply hostname-specific title + OG meta tags once on mount
  useEffect(() => {
    applyHostnameMeta();
    initGA();
  }, []);

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
        {/* On portal hostnames (xxl.co.il, www.xxl.co.il, localhost?portal=1),
            "/" renders PortalPage. On super.xxl.co.il this Route is absent,
            so "/" falls through to the "/*" catch-all → AppShell. */}
        {isPortalHostname() ? (
          <Route path="/" element={<PortalPage />} />
        ) : null}
        {/* All existing supermarket app routes — untouched */}
        <Route path="/*" element={<AppShell />} />
      </Routes>
    </>
  );
}
