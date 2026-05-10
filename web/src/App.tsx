import { Routes, Route } from 'react-router-dom';
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

export default function App() {
  return (
    <BasketProvider>
      <FavoritesProvider>
        <Toaster position="top-center" duration={4000} dir="rtl" />
        <BasketDrawer />
        <Header />
        <Routes>
          <Route path="/"          element={<HomePage />} />
          <Route path="/login"     element={<LoginPage />} />
          <Route path="/signup"    element={<SignupPage />} />
          <Route path="/baskets"   element={<MyBasketsPage />} />
          <Route path="/favorites" element={<FavoritesPage />} />
        </Routes>
      </FavoritesProvider>
    </BasketProvider>
  );
}
