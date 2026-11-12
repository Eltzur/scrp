import { Link } from 'react-router-dom';
import { NOT_FOUND_TITLE } from '../utils/seoMeta';

/**
 * SU11A-80 (SU11A-79 M1): the catch-all route. Before it, an unknown path
 * showed the header and footer around an empty page.
 *
 * Title, noindex and no canonical come from utils/seoMeta.ts (an unknown path).
 * nginx still answers 200 for every path (the SPA fallback); a real 404 status
 * is an nginx change (handoff SU11A-80, "next").
 */
export const NOT_FOUND_TEXT = 'ייתכן שהקישור שגוי או שהדף הוסר.';
export const NOT_FOUND_HOME = 'חזרה לדף הבית';

export default function NotFoundPage() {
  return (
    <main id="main" dir="rtl" className="max-w-xl mx-auto px-4 py-20 text-center">
      <h1 className="text-2xl font-bold text-gray-900">{NOT_FOUND_TITLE}</h1>
      <p className="mt-3 text-gray-700">{NOT_FOUND_TEXT}</p>
      <Link
        to="/"
        className="inline-block mt-6 px-5 py-2 rounded-lg bg-emerald-700 text-white font-medium hover:bg-emerald-800
                   focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500 focus-visible:ring-offset-2"
      >
        {NOT_FOUND_HOME}
      </Link>
    </main>
  );
}
