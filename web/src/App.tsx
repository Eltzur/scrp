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
// Portal routes — rendered without the supermarket app shell
import PortalPage from './pages/PortalPage';
import VacationPage from './pages/VacationPage';
import FashionPage from './pages/FashionPage';
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
        </Routes>
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

  // Track SPA route changes (GA4 pageview per navigation)
  useEffect(() => {
    trackPageview(location.pathname);
  }, [location.pathname]);

  return (
    <>
      <CookieBanner />
      <Routes>
        {/* Portal routes — standalone, no supermarket header/basket/auth providers */}
        <Route path="/portal-preview" element={<PortalPage />} />
        <Route path="/vacation"       element={<VacationPage />} />
        <Route path="/fashion"        element={<FashionPage />} />
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
