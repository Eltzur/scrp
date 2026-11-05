/**
 * SU11A-68: the home page's "קטגוריות" section: the departments as links
 * (from /categories/browse-tree, the same cached query as the browse pages).
 * A lazy chunk; the section keeps its height while loading, so nothing moves.
 */
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getBrowseTree } from '../../api/categoryBrowse';
import { nodeName } from '../../utils/categoryView';
import { K } from '../../pages/categories/strings';

export default function HomeCategories() {
  const { t, i18n } = useTranslation();
  const en = i18n.language.startsWith('en');
  const tree = useQuery({ queryKey: ['browse-tree'], queryFn: ({ signal }) => getBrowseTree(signal), staleTime: 10 * 60 * 1000, retry: 1 });
  const depts = (tree.data?.departments ?? []).filter(d => d.count > 0);
  if (tree.isError) return null;
  return (
    <section aria-labelledby="home-categories-title" className="py-2 min-h-[7rem]">
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <h2 id="home-categories-title" className="text-lg font-bold text-[#022C22]">{t(`${K}.home_title`)}</h2>
        <Link to="/categories" className="text-sm font-medium text-emerald-800 underline underline-offset-2 hover:text-emerald-900">
          {t(`${K}.home_all`)}
        </Link>
      </div>
      <ul className="flex flex-wrap gap-2">
        {depts.map(d => (
          <li key={d.id}>
            <Link
              to={`/categories/${d.id}`}
              className="inline-flex items-center min-h-[36px] px-3 py-1.5 rounded-full border border-gray-300 bg-white
                         text-sm text-gray-800 hover:border-emerald-600 hover:text-emerald-800"
            >
              {nodeName(d, en)}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
