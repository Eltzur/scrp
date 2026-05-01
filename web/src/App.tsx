import { Routes, Route } from 'react-router-dom';
import { Toaster } from 'sonner';
import { BasketProvider } from './components/BasketContext';
import BasketDrawer from './components/BasketDrawer';
import Header from './components/Header';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import SignupPage from './pages/SignupPage';
import MyBasketsPage from './pages/MyBasketsPage';

export default function App() {
  return (
    <BasketProvider>
      <Toaster position="top-center" duration={4000} dir="rtl" />
      <BasketDrawer />
      <Header />
      <Routes>
        <Route path="/"        element={<HomePage />} />
        <Route path="/login"   element={<LoginPage />} />
        <Route path="/signup"  element={<SignupPage />} />
        <Route path="/baskets" element={<MyBasketsPage />} />
      </Routes>
    </BasketProvider>
  );
}
