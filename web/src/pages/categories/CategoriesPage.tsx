/**
 * SU11A-67: category browse pages (design docs/catalog/su11a66_categories_browse_design.md).
 *
 *   /categories        the department grid (from /categories/browse-tree)
 *   /categories/:id    a department, category or sub-category: breadcrumbs, the
 *                      linked sub-nodes as chips, filters (city / chain / sort /
 *                      רק במבצע) and the search-result card grid with promo badges
 *                      and add-to-basket (ResultsList), "טען עוד" paging.
 *
 * The view lives in the URL (utils/categoryView.ts); the city defaults to the
 * remembered one (utils/city.ts) like the search and promos pages. A lazy chunk
 * with its own strings (./strings.ts). SEO (pre-render, sitemap) is SU11A-68:
 * until then these paths are noindex (utils/seoMeta.ts treats them as unknown).
 */
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useQuery, keepPreviousData } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { isAxiosError } from 'axios';
import { ChevronLeft, Loader2, Search } from 'lucide-react';
import { getBrowseTree, getCategoryItems, type BrowseNode, type CategoryItemsResult } from '../../api/categoryBrowse';
import type { SearchResult } from '../../api/client';
import { useChains, useCities } from '../../api/hooks';
import ResultsList from '../../components/ResultsList';
import { rememberCity, rememberedCity } from '../../utils/city';
import {
  CATEGORY_Q_MAX, CATEGORY_SORTS, categoryParams, categorySearchText, findNode, hasViewFilters, isNodeId, itemsRequest,
  nextOffset, nodeName, readCategoryView, searchPageUrl, type CategorySort,
} from '../../utils/categoryView';
import { applyCategoryHead, categoryHead, removeCategoryHead } from '../../utils/categorySeo';
import { K } from './strings';

const TREE_STALE = 10 * 60 * 1000;
/** SU11A-68: one request per typing pause (the items path is in nginx's xxl_heavy group). */
export const CATEGORY_SEARCH_DEBOUNCE_MS = 350;

function useTree() {
  return useQuery({
    queryKey: ['browse-tree'],
    queryFn: ({ signal }) => getBrowseTree(signal),
    staleTime: TREE_STALE,
    retry: 1,
  });
}

function Crumbs({ path, en }: { path: { id: string; name_he: string; name_en: string }[]; en: boolean }) {
  const { t } = useTranslation();
  return (
    <nav aria-label={t(`${K}.breadcrumbs`)} className="text-sm text-gray-600 mb-2">
      <ol className="flex flex-wrap items-center gap-1">
        <li><Link to="/categories" className="hover:text-emerald-700 underline-offset-2 hover:underline">{t(`${K}.home`)}</Link></li>
        {path.map((p, i) => (
          <li key={p.id} className="flex items-center gap-1">
            <ChevronLeft size={14} aria-hidden="true" className="rtl:rotate-0 ltr:rotate-180" />
            {i === path.length - 1
              ? <span aria-current="page" className="font-semibold text-gray-900">{nodeName(p, en)}</span>
              : <Link to={`/categories/${p.id}`} className="hover:text-emerald-700 underline-offset-2 hover:underline">{nodeName(p, en)}</Link>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

function NodeChips({ nodes, en, label }: { nodes: { id: string; name_he: string; name_en: string; count: number }[]; en: boolean; label: string }) {
  const { t } = useTranslation();
  if (!nodes.length) return null;
  return (
    <nav aria-label={label} className="mb-4">
      <ul className="flex flex-wrap gap-2">
        {nodes.map(n => (
          <li key={n.id}>
            <Link
              to={`/categories/${n.id}`}
              className="inline-flex items-center gap-1.5 min-h-[36px] px-3 py-1.5 rounded-full border border-gray-300 bg-white
                         text-sm text-gray-800 hover:border-emerald-600 hover:text-emerald-800"
            >
              {nodeName(n, en)}
              <span className="text-xs text-gray-600">{t(`${K}.items_count`, { count: n.count })}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function Departments() {
  const { t, i18n } = useTranslation();
  const en = i18n.language.startsWith('en');
  const tree = useTree();
  if (tree.isError) return <LoadError onRetry={() => tree.refetch()} />;
  return (
    <>
      <h1 className="text-2xl font-bold text-gray-900 mb-1">{t(`${K}.title`)}</h1>
      <p className="text-sm text-gray-600 mb-4">{t(`${K}.intro`)}</p>
      {tree.isLoading ? (
        <p role="status" className="flex items-center gap-2 text-sm text-gray-600"><Loader2 size={14} className="animate-spin" aria-hidden="true" />{t(`${K}.loading`)}</p>
      ) : (
        <ul className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {(tree.data?.departments ?? []).filter(d => d.count > 0).map((d: BrowseNode) => (
            <li key={d.id}>
              <Link
                to={`/categories/${d.id}`}
                className="block h-full rounded-xl border border-gray-200 bg-white p-4 hover:border-emerald-600 hover:shadow-sm"
              >
                <span className="block font-semibold text-gray-900">{nodeName(d, en)}</span>
                <span className="block mt-1 text-xs text-gray-600">{t(`${K}.items_count`, { count: d.count })}</span>
                {d.children.length > 0 && (
                  <span className="block mt-2 text-xs text-gray-700 line-clamp-2">
                    {d.children.slice(0, 4).map(c => nodeName(c, en)).join(' · ')}
                  </span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function LoadError({ onRetry, notFound }: { onRetry?: () => void; notFound?: boolean }) {
  const { t } = useTranslation();
  return (
    <div role="alert" className="rounded-xl border border-gray-200 bg-white p-6 text-center">
      <p className="text-gray-800">{t(notFound ? `${K}.not_found` : `${K}.error`)}</p>
      <div className="mt-3 flex justify-center gap-3">
        {!notFound && onRetry && (
          <button type="button" onClick={onRetry} className="px-4 py-2 rounded-lg bg-emerald-700 text-white text-sm font-medium hover:bg-emerald-800">
            {t(`${K}.retry`)}
          </button>
        )}
        <Link to="/categories" className="px-4 py-2 rounded-lg border border-gray-300 text-sm font-medium text-gray-800 hover:border-emerald-600">
          {t(`${K}.back`)}
        </Link>
      </div>
    </div>
  );
}

function CategoryPage({ id }: { id: string }) {
  const { t, i18n } = useTranslation();
  const en = i18n.language.startsWith('en');
  const [params, setParams] = useSearchParams();
  const view = useMemo(() => readCategoryView(params), [params]);
  const { data: cities = [] } = useCities();
  const { data: chains = [] } = useChains();
  const tree = useTree();
  const remembered = useMemo(() => {
    const c = rememberedCity();
    return c && (cities.length === 0 || cities.some(x => x.city === c)) ? c : '';
  }, [cities]);
  const city = view.city ?? remembered;

  useEffect(() => { if (view.city) rememberCity(view.city); }, [view.city]);

  const set = (changes: Parameters<typeof categoryParams>[1]) =>
    setParams(prev => categoryParams(prev, changes), { replace: true });

  // SU11A-68: search inside the category. The box updates the URL after a
  // pause; Back / a shared link changes q under the box, and the box follows.
  const [qInput, setQInput] = useState(view.q);
  useEffect(() => {
    if (qInput.trim() === view.q.trim()) return;
    const h = setTimeout(() => set({ q: qInput }), CATEGORY_SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- set is stable in effect
  }, [qInput]);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror the URL into the input
  useEffect(() => { setQInput(cur => (cur.trim() === view.q.trim() ? cur : view.q)); }, [view.q]);
  const qText = categorySearchText(view.q);

  const list = useInfiniteQuery({
    queryKey: ['category-items', id, city, view.chain, view.sort, view.promo, qText],
    queryFn: ({ pageParam, signal }) => getCategoryItems(id, itemsRequest({ ...view, city }, '', pageParam), signal),
    initialPageParam: 0,
    getNextPageParam: (last: CategoryItemsResult, all: CategoryItemsResult[]) => nextOffset(last, all),
    placeholderData: keepPreviousData,
    retry: (n, err) => !(isAxiosError(err) && err.response?.status && err.response.status < 500) && n < 1,
  });

  const first = list.data?.pages[0];
  const notFound = isAxiosError(list.error) && list.error.response?.status === 404;
  const node = findNode(tree.data, id);
  const children = first?.children ?? node?.children ?? [];
  const path = first?.path ?? [];
  const title = first ? nodeName(first.category, en) : node ? nodeName(node, en) : '';

  const result: SearchResult | undefined = useMemo(() => {
    if (!list.data) return undefined;
    const pages = list.data.pages;
    const last = pages[pages.length - 1];
    return {
      query: title || id,
      total_matches: pages[0].total,
      comparable_count: 0,
      has_more: list.hasNextPage ?? last.has_more,
      items: pages.flatMap(p => p.items),
    };
  }, [list.data, list.hasNextPage, title, id]);

  // SU11A-68: the node's own title / description / canonical / breadcrumbs,
  // after App's generic tags for the path (a timeout: a cached page renders in
  // the same commit as the route change, before App's effect).
  const filteredUrl = hasViewFilters(params);
  useEffect(() => {
    if (!first) return;
    const h = setTimeout(() => applyCategoryHead(categoryHead(first.path, first.count, filteredUrl)), 0);
    return () => clearTimeout(h);
  }, [first, filteredUrl]);
  useEffect(() => removeCategoryHead, []);

  if (notFound) return <LoadError notFound />;

  const filtered = !!(view.chain || view.promo || qText);
  const countText = first
    ? t(first.total_exact ? `${K}.items_count` : `${K}.items_about`, { count: first.total })
    : undefined;
  const sortLabel: Record<CategorySort, string> = {
    popular: t(`${K}.sort_popular`), cheapest: t(`${K}.sort_cheapest`), name: t(`${K}.sort_name`),
  };

  return (
    <>
      <Crumbs path={path.length ? path : node ? [node] : []} en={en} />
      <h1 className="text-2xl font-bold text-gray-900 mb-3">{title || ' '}</h1>
      <NodeChips nodes={children} en={en} label={t(`${K}.children_label`)} />

      <form
        aria-label={t(`${K}.filters_label`)}
        onSubmit={e => { e.preventDefault(); set({ q: qInput }); }}
        className="flex flex-wrap items-end gap-3 mb-4 rounded-xl border border-gray-200 bg-white p-3"
      >
        <label className="flex flex-col text-xs font-medium text-gray-700 grow min-w-[12rem]">
          {t(`${K}.search_label`, { name: title })}
          <span className="relative mt-1">
            <Search size={14} aria-hidden="true" className="absolute top-1/2 -translate-y-1/2 start-2 text-gray-500" />
            <input
              type="search"
              value={qInput}
              maxLength={CATEGORY_Q_MAX}
              onChange={e => setQInput(e.target.value)}
              placeholder={t(`${K}.search_placeholder`)}
              className="w-full min-h-[36px] rounded-lg border border-gray-300 bg-white ps-7 pe-2 text-sm text-gray-900"
            />
          </span>
        </label>
        <label className="flex flex-col text-xs font-medium text-gray-700">
          {t(`${K}.city_label`)}
          <select
            value={city}
            onChange={e => set({ city: e.target.value })}
            className="mt-1 min-h-[36px] rounded-lg border border-gray-300 bg-white px-2 text-sm text-gray-900"
          >
            <option value="">{t(`${K}.all_cities`)}</option>
            {cities.map(c => <option key={c.city} value={c.city}>{c.city}</option>)}
          </select>
        </label>
        <label className="flex flex-col text-xs font-medium text-gray-700">
          {t(`${K}.chain_label`)}
          <select
            value={view.chain}
            onChange={e => set({ chain: e.target.value })}
            className="mt-1 min-h-[36px] rounded-lg border border-gray-300 bg-white px-2 text-sm text-gray-900"
          >
            <option value="">{t(`${K}.all_chains`)}</option>
            {chains.map(c => <option key={c.chain_id} value={c.chain_id}>{c.name ?? c.chain_id}</option>)}
          </select>
        </label>
        <label className="flex flex-col text-xs font-medium text-gray-700">
          {t(`${K}.sort_label`)}
          <select
            value={view.sort}
            onChange={e => set({ sort: e.target.value as CategorySort })}
            className="mt-1 min-h-[36px] rounded-lg border border-gray-300 bg-white px-2 text-sm text-gray-900"
          >
            {CATEGORY_SORTS.map(s => <option key={s} value={s}>{sortLabel[s]}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 min-h-[36px] text-sm text-gray-800">
          <input
            type="checkbox"
            checked={view.promo}
            onChange={e => set({ promo: e.target.checked })}
            className="h-4 w-4 accent-emerald-700"
          />
          {t(`${K}.only_promo`)}
        </label>
      </form>

      {qText && (
        <p className="mb-3 text-sm text-gray-700">
          {first?.corrected_from && <span className="me-2">{t(`${K}.corrected`, { q: first.q })}</span>}
          <Link to={searchPageUrl(qText, id)} className="font-medium text-emerald-800 underline underline-offset-2 hover:text-emerald-900">
            {t(`${K}.search_all`, { q: qText })}
          </Link>
        </p>
      )}

      {result && result.items.length === 0 && !list.isPlaceholderData ? (
        <div className="rounded-xl border border-gray-200 bg-white p-6 text-center" role="status">
          <p className="text-gray-800">{t(`${K}.empty`)}</p>
          {filtered && (
            <button
              type="button"
              onClick={() => { setQInput(''); set({ chain: '', promo: false, q: '' }); }}
              className="mt-3 px-4 py-2 rounded-lg border border-gray-300 text-sm font-medium text-gray-800 hover:border-emerald-600"
            >
              {t(`${K}.clear_filters`)}
            </button>
          )}
        </div>
      ) : (
        <ResultsList
          result={result}
          isLoading={list.isLoading}
          isFetching={list.isFetching}
          isError={list.isError}
          isBusy={isAxiosError(list.error) && [429, 503].includes(list.error.response?.status ?? 0)}
          query={title || id}
          onRetry={() => list.refetch()}
          onLoadMore={() => list.fetchNextPage()}
          isLoadingMore={list.isFetchingNextPage}
          countText={countText}
        />
      )}
    </>
  );
}

export default function CategoriesPage() {
  const { id } = useParams();
  return (
    <main className="max-w-6xl mx-auto px-3 sm:px-4 py-6">
      {id === undefined ? <Departments /> : isNodeId(id) ? <CategoryPage key={id} id={id} /> : <LoadError notFound />}
    </main>
  );
}
