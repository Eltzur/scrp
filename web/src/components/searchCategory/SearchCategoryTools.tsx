/**
 * SU11A-68: the search page's category tools, a lazy chunk (with the browse
 * strings), so the main bundle carries none of it:
 *   - a labelled select: department › category › sub-category, from
 *     /categories/browse-tree (linked nodes only; tobacco is never listed);
 *   - "הצג רק ב<קטגוריה>" when most of the results share one node
 *     (GET /categories/dominant on the first page's barcodes).
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { getBrowseTree, getDominantCategory, type BrowseNode } from '../../api/categoryBrowse';
import { nodeName } from '../../utils/categoryView';
import { K } from '../../pages/categories/strings';

function treeOptions(departments: BrowseNode[], en: boolean): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = [];
  const walk = (n: BrowseNode, depth: number) => {
    out.push({ value: n.id, label: `${'  '.repeat(depth * 2)}${nodeName(n, en)}` });
    n.children.forEach(c => walk(c, depth + 1));
  };
  departments.filter(d => d.count > 0).forEach(d => walk(d, 0));
  return out;
}

export default function SearchCategoryTools({ category, onChange, itemCodes }: {
  category: string | null;
  onChange: (id: string | null) => void;
  itemCodes: string[];
}) {
  const { t, i18n } = useTranslation();
  const en = i18n.language.startsWith('en');
  const tree = useQuery({ queryKey: ['browse-tree'], queryFn: ({ signal }) => getBrowseTree(signal), staleTime: 10 * 60 * 1000, retry: 1 });
  const options = useMemo(() => treeOptions(tree.data?.departments ?? [], en), [tree.data, en]);
  const codes = useMemo(() => itemCodes.slice(0, 30), [itemCodes]);
  const hint = useQuery({
    queryKey: ['dominant-category', codes],
    queryFn: ({ signal }) => getDominantCategory(codes, signal),
    enabled: !category && codes.length >= 4,
    staleTime: 5 * 60 * 1000,
    retry: 0,
  });
  // a stale value from the tree when the API's id is unknown to it: show the plain id
  const known = !category || options.some(o => o.value === category);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="flex items-center gap-1.5 text-sm text-gray-700">
        <span>{t(`${K}.category_filter`)}</span>
        <select
          value={category ?? ''}
          onChange={e => onChange(e.target.value || null)}
          className="min-h-[34px] max-w-[14rem] rounded-lg border border-gray-300 bg-white px-2 text-sm text-gray-900
                     focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          <option value="">{t(`${K}.all_categories`)}</option>
          {!known && category && <option value={category}>{category}</option>}
          {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </label>
      {!category && hint.data && (
        <button
          type="button"
          onClick={() => onChange(hint.data!.id)}
          className="min-h-[34px] rounded-full border border-emerald-600 px-3 text-sm font-medium text-emerald-800
                     hover:bg-emerald-50 focus:outline-none focus:ring-2 focus:ring-emerald-500"
        >
          {t(`${K}.only_in`, { name: nodeName(hint.data, en) })}
        </button>
      )}
    </div>
  );
}
