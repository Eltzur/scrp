import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { ChevronDown, Loader2, AlertCircle, Search, SlidersHorizontal, X } from 'lucide-react';
import clsx from 'clsx';
import type {
  CategoryNode, FlatPromoItem, GroupedPromoItem, PromoChain, PromoSort, PromoTypeFilter,
} from '../api/client';
import { getCategoryTree, getFlatPromos, getGroupedPromos, getPromoChains, getPromotedPromos } from '../api/client';
import { useCities } from '../api/hooks';
import { rememberCity, rememberedCity } from '../utils/city';
import { promoSearchText, promosMode, readView, withChanges } from '../utils/promosView';
import Highlight from '../components/Highlight';
import { GIFT_COUPON_LABEL, giftCouponView, giftQtyText } from '../utils/giftCoupon';

const PAGE_SIZE = 300;      // grouped (one chain)
const FLAT_PAGE_SIZE = 30;  // SU11A-60: the cross-chain list
const SEARCH_DEBOUNCE_MS = 300;
const ENDING_SOON_HOURS = 48;

const SELECT_CLS =
  'border border-gray-300 rounded-lg text-sm text-gray-700 bg-white px-3 py-1.5 ' +
  'hover:border-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-500 ' +
  'disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-gray-300';

// Labelled as explicit ranges, not "up to": "עד 10%" is the only open-ended one
// because the band genuinely starts at 0.
const BANDS: { value: string; label: string }[] = [
  { value: '0-10',  label: 'עד 10%'  },
  { value: '11-25', label: '11–25%' },
  { value: '26-50', label: '26–50%' },
  { value: '51-75', label: '51–75%' },
  { value: '76-99', label: '76–99%' },
];

// Gift deals sit at exactly 100% off, which falls in NO band (bands are
// upper-inclusive and stop at 99), so this chip is the only way to reach them.
// SU11A-65: gift coupons have their own chip; the other chips exclude them.
const PROMO_TYPES: { value: PromoTypeFilter; label: string }[] = [
  { value: 'gift',     label: '1+1 / מתנה'    },
  { value: 'bundle',   label: "כמה יח' ב-₪"   },
  { value: 'fixed',    label: 'מחיר מבצע'     },
  { value: 'discount', label: '% הנחה'        },
  { value: 'basket',   label: 'בתנאי / מעל סכום' },
  { value: 'gift_coupon', label: GIFT_COUPON_LABEL },
];

const SORTS: { value: PromoSort; label: string }[] = [
  { value: 'discount', label: 'הנחה גדולה'      },
  { value: 'savings',  label: 'חיסכון בשקלים'   },
  { value: 'ending',   label: 'מסתיים בקרוב'    },
];

function fmtPrice(n: number): string {
  return new Intl.NumberFormat('he-IL', {
    style: 'currency', currency: 'ILS', minimumFractionDigits: 2,
  }).format(n);
}

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  return `בתוקף עד ${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()}`;
}

/** Group the flat rows into chain → city → branch, PRESERVING arrival order.
 *  The endpoint already sorts chain → city → branch → <sort> within branch, so
 *  Maps (which keep insertion order) reproduce that hierarchy without
 *  re-sorting — re-sorting here would silently break the within-branch order
 *  the user just chose. */
type BranchGroup = { branch: string; rows: GroupedPromoItem[] };
type CityGroup   = { city: string; branches: BranchGroup[] };
type ChainGroup  = { chain: string; cities: CityGroup[]; count: number };

function groupRows(rows: GroupedPromoItem[]): ChainGroup[] {
  const chains = new Map<string, Map<string, Map<string, GroupedPromoItem[]>>>();
  for (const r of rows) {
    const chain  = r.chain_name ?? r.chain_id;
    const city   = r.city   ?? '—';
    const branch = r.branch ?? '—';
    if (!chains.has(chain)) chains.set(chain, new Map());
    const cityMap = chains.get(chain)!;
    if (!cityMap.has(city)) cityMap.set(city, new Map());
    const branchMap = cityMap.get(city)!;
    if (!branchMap.has(branch)) branchMap.set(branch, []);
    branchMap.get(branch)!.push(r);
  }
  return Array.from(chains, ([chain, cityMap]) => ({
    chain,
    count: Array.from(cityMap.values())
      .reduce((n, bm) => n + Array.from(bm.values()).reduce((m, a) => m + a.length, 0), 0),
    cities: Array.from(cityMap, ([city, branchMap]) => ({
      city,
      branches: Array.from(branchMap, ([branch, rs]) => ({ branch, rows: rs })),
    })),
  }));
}

function Chip({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={clsx(
        'text-xs font-medium px-2.5 py-1 rounded-full border transition-colors whitespace-nowrap',
        active
          ? 'bg-emerald-700 text-white border-emerald-600'
          : 'bg-white text-gray-600 border-gray-300 hover:border-emerald-400',
      )}
    >
      {label}
    </button>
  );
}

/** Minimum-spend condition, shown on both card shapes. */
function ConditionBadge({ amount }: { amount: number | null }) {
  if (amount == null || amount <= 0) return null;
  return (
    <span className="inline-block text-[11px] font-medium px-1.5 py-0.5 rounded bg-sky-50 text-sky-800 border border-sky-200">
      מעל {fmtPrice(amount)}
    </span>
  );
}

/** SU11A-58: paid placement, chosen in the admin console. The label is
 *  mandatory on a sponsored card, and is text (not colour alone). */
function SponsoredBadge({ item }: { item: GroupedPromoItem }) {
  if (!item.sponsored) return null;
  return (
    <span className="inline-block text-[11px] font-semibold px-1.5 py-0.5 rounded bg-gray-100 text-gray-700 border border-gray-300">
      ממומן
    </span>
  );
}

/** Basket promos: conditional / spend-threshold deals with no per-unit price.
 *  Deliberately a different shape from a unit card — no struck-through shelf
 *  price, no unit price, no % badge, because none of those exist for these
 *  rows and inventing them is exactly the bug this whole workstream fixed. */
function BasketCard({ item, term }: { item: GroupedPromoItem; term?: string }) {
  const hasThreshold = item.min_purchase_amount != null && item.min_purchase_amount > 0;
  return (
    <div className="flex items-start justify-between gap-3 px-3 py-2.5 border-t border-gray-100 first:border-t-0 bg-sky-50/30">
      <div className="min-w-0 flex-1">
        {/* Description leads here: for these rows it carries the actual terms
            (common for weighted goods — fish, meat, produce). */}
        <p className="text-sm text-gray-900 leading-snug font-medium" dir="auto">
          <Highlight text={item.promo_description ?? item.product_name ?? item.item_code} term={term} />
        </p>
        {item.product_name && item.promo_description && (
          <p className="text-[11px] text-gray-500 mt-0.5" dir="auto"><Highlight text={item.product_name} term={term} /></p>
        )}
        {item.promo_end && (
          <p className="text-[11px] text-gray-500 mt-1">{fmtDate(item.promo_end)}</p>
        )}
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <SponsoredBadge item={item} />
        {hasThreshold
          ? <ConditionBadge amount={item.min_purchase_amount} />
          : (
            <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-200 whitespace-nowrap">
              מבצע מותנה
            </span>
          )}
      </div>
    </div>
  );
}

/** SU11A-65: a free unit with a coupon. Its value is conditional, so it shows
 *  "מתנה בקופון", the free quantity and the condition, and the shelf price as
 *  plain text: never a %, never a struck-through price. */
function GiftCouponCard({ item, term }: { item: GroupedPromoItem; term?: string }) {
  const g = giftCouponView(item);
  const qty = giftQtyText(g.qty);
  return (
    <div className="flex items-start justify-between gap-3 px-3 py-2.5 border-t border-gray-100 first:border-t-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm text-gray-900 leading-snug" dir="auto">
          <Highlight text={item.product_name ?? item.promo_description ?? item.item_code} term={term} />
        </p>
        <div className="flex flex-wrap items-center gap-1 mt-1">
          {qty && (
            <span className="inline-block text-[11px] font-medium px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
              {qty}
            </span>
          )}
          {g.condition && (
            <span className="inline-block text-[11px] font-medium px-1.5 py-0.5 rounded bg-sky-50 text-sky-800 border border-sky-200">
              {g.condition}
            </span>
          )}
          <SponsoredBadge item={item} />
        </div>
        {item.promo_description && (
          <p className="text-[11px] text-gray-500 mt-1" dir="auto"><Highlight text={item.promo_description} term={term} /></p>
        )}
        {item.promo_end && (
          <p className="text-[11px] text-gray-500 mt-1">{fmtDate(item.promo_end)}</p>
        )}
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
        <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 whitespace-nowrap">
          {GIFT_COUPON_LABEL}
        </span>
        {item.shelf_price != null && (
          <span className="text-[11px] text-gray-600 whitespace-nowrap">מחיר מדף {fmtPrice(item.shelf_price)}</span>
        )}
      </div>
    </div>
  );
}

/** Exported for scripts/sponsored-label.test.mjs (SU11A-58). SU11A-62: term =
 *  the search text, marked in the product name. */
export function PromoRow({ item, term }: { item: GroupedPromoItem; term?: string }) {
  if (item.promo_kind === 'basket') return <BasketCard item={item} term={term} />;
  if (item.gift_coupon) return <GiftCouponCard item={item} term={term} />;

  const isBundle = item.min_qty != null && item.min_qty > 1;
  // A zero unit price is never a real price — nothing is bought for ₪0.00. It
  // marks the free half of a gift/1+1 deal, which the generic formula would
  // otherwise render as "-100%, ₪0.00". Keyed on the price rather than on
  // reward_type because that code is chain-specific and unreliable: Victory
  // encodes its 1+1 as reward_type=10, not 1.
  const isFreebie = item.unit_price === 0 || item.discount_price === 0;
  const freebieLabel = /1\s*\+\s*1/.test(item.promo_description ?? '') ? '1+1' : 'מבצע';

  return (
    <div className="flex items-start justify-between gap-3 px-3 py-2.5 border-t border-gray-100 first:border-t-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm text-gray-900 leading-snug" dir="auto">
          <Highlight text={item.product_name ?? item.promo_description ?? item.item_code} term={term} />
        </p>
        <div className="flex flex-wrap items-center gap-1 mt-1">
          {/* Suppressed for freebies: a gift promo has discount_price 0, so this
              would read "5 units for ₪0.00". The description carries the terms. */}
          {isBundle && !isFreebie && (
            <span className="inline-block text-[11px] font-medium px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
              {Math.round(item.min_qty!)} יח' ב-{fmtPrice(item.discount_price ?? 0)}
            </span>
          )}
          <ConditionBadge amount={item.min_purchase_amount} />
          <SponsoredBadge item={item} />
        </div>
        {isFreebie && item.promo_description && (
          <p className="text-[11px] text-gray-500 mt-1" dir="auto">{item.promo_description}</p>
        )}
        {item.promo_end && (
          <p className="text-[11px] text-gray-500 mt-1">{fmtDate(item.promo_end)}</p>
        )}
      </div>

      <div className="flex flex-col items-end gap-1 shrink-0" dir="ltr">
        {isFreebie ? (
          <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">
            {freebieLabel}
          </span>
        ) : item.discount_pct != null && (
          <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">
            -{Math.round(item.discount_pct)}%
          </span>
        )}
        <div className="flex items-baseline gap-1.5">
          {item.shelf_price != null && (
            <span className={clsx(
              'text-xs',
              isFreebie ? 'text-gray-500' : 'text-gray-500 line-through',
            )}>
              {fmtPrice(item.shelf_price)}
            </span>
          )}
          {!isFreebie && item.unit_price != null && (
            <span className="text-sm font-bold text-emerald-700">{fmtPrice(item.unit_price)}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function Collapsible({
  title, subtitle, count, level, children,
}: {
  title: string; subtitle?: string; count?: number;
  level: 'chain' | 'city' | 'branch'; children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className={clsx(level === 'chain' && 'bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden')}>
      <button
        onClick={() => setOpen(o => !o)}
        className={clsx(
          'w-full flex items-center justify-between gap-2 text-right transition-colors',
          level === 'chain'  && 'px-4 py-3 bg-gray-50 hover:bg-gray-100 border-b border-gray-200',
          level === 'city'   && 'px-4 py-2 hover:bg-gray-50',
          level === 'branch' && 'px-3 py-1.5 hover:bg-gray-50',
        )}
      >
        <span className="flex items-baseline gap-2 min-w-0">
          <span className={clsx(
            'truncate',
            level === 'chain'  && 'font-bold text-gray-900',
            level === 'city'   && 'font-semibold text-gray-700 text-sm',
            level === 'branch' && 'font-medium text-gray-600 text-sm',
          )} dir="auto">{title}</span>
          {subtitle && <span className="text-xs text-gray-500 truncate" dir="auto">{subtitle}</span>}
          {count != null && <span className="text-xs text-gray-500 shrink-0">({count})</span>}
        </span>
        <ChevronDown
          size={16}
          className={clsx('text-gray-500 shrink-0 transition-transform', !open && '-rotate-90')}
        />
      </button>
      {open && <div>{children}</div>}
    </div>
  );
}

/** SU11A-60: a cross-chain card (flat list, מבצעים מקודמים): the chain and the
 *  representative branch on top, then the usual promo row. SU11A-62: with
 *  search text, a promoted card shows its best-matching product and how many
 *  more of the promotion's products match. */
export function FlatCard({ item, term }: { item: FlatPromoItem; term?: string }) {
  const { t } = useTranslation();
  const more = item.branch_count - 1;
  const moreMatches = term && item.item_count != null ? item.item_count - 1 : 0;
  return (
    <li className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <p className="px-3 pt-2 text-xs text-gray-600" dir="auto">
        <span className="font-semibold text-gray-900">{item.chain_name ?? item.chain_id}</span>
        {' · '}{item.branch ?? '—'}
        {more > 0 && <> {more === 1 ? t('promos.one_more_branch') : t('promos.more_branches', { count: more })}</>}
      </p>
      <PromoRow item={item} term={term} />
      {moreMatches > 0 && (
        <p className="px-3 pb-2 -mt-1 text-[11px] text-gray-600" dir="auto">
          {moreMatches === 1 ? t('promos.one_more_match') : t('promos.more_matches', { count: moreMatches })}
        </p>
      )}
    </li>
  );
}

/** Departments, categories and sub-categories in tree order, for the select. */
function categoryOptions(nodes: CategoryNode[], en: boolean) {
  const kids = new Map<string | null, CategoryNode[]>();
  for (const n of nodes) {
    const k = kids.get(n.parent_id) ?? [];
    k.push(n);
    kids.set(n.parent_id, k);
  }
  const out: { id: string; label: string; level: number }[] = [];
  const walk = (parent: string | null) => {
    for (const n of kids.get(parent) ?? []) {
      out.push({ id: n.id, label: '  '.repeat(n.level - 1) + ((en && n.name_en) || n.name_he), level: n.level });
      walk(n.id);
    }
  };
  walk(null);
  return out;
}

const VIEW_ALLOWED = {
  sorts: SORTS.map(x => x.value as string),
  bands: BANDS.map(x => x.value),
  types: PROMO_TYPES.map(x => x.value as string),
};

export default function PromosPage() {
  const { t, i18n } = useTranslation();
  const en = i18n.language.startsWith('en');
  const { data: cityInfos = [] } = useCities();
  const tree = useQuery({ queryKey: ['category-tree'], queryFn: getCategoryTree, staleTime: 60 * 60 * 1000, retry: 1 });

  // SU11A-60: the view lives in the URL (shareable, Back works); city=''
  // is "all cities". The city never waits on anything: URL -> remembered ->
  // all cities, synchronously, on a direct load and on an in-app link alike
  // (the header link drops ?city while this page stays mounted).
  const [params, setParams] = useSearchParams();
  const view = useMemo(() => readView(params, VIEW_ALLOWED), [params]);
  const remembered = useMemo(() => {
    const c = rememberedCity();
    return c && (cityInfos.length === 0 || cityInfos.some(x => x.city === c)) ? c : '';
  }, [cityInfos]);
  const city = view.city ?? remembered;
  const { branch, q, ending: endingSoon } = view;
  const chainId = view.chain;
  const category = view.cat;
  const sort = view.sort as PromoSort;
  const bands = view.bands;
  const types = view.types as PromoTypeFilter[];

  const update = (changes: Record<string, string | null>, replace = false) =>
    setParams(prev => withChanges(prev, changes), { replace });

  const [chains,  setChains]  = useState<PromoChain[]>([]);
  const [qInput,  setQInput]  = useState(q);
  const [filtersOpen, setFiltersOpen] = useState(false); // mobile panel

  // Branch options are captured from an UNFILTERED-by-branch result and kept in
  // their own state. Deriving them from `rows` directly would collapse the list
  // to the single selected branch the moment one is chosen.
  const [branchOpts, setBranchOpts] = useState<{ fk: number; name: string }[]>([]);

  useEffect(() => { getPromoChains().then(setChains).catch(() => setChains([])); }, []);

  // Write the city into the URL when it has none (shareable view); replace,
  // so Back does not stop on the city-less entry.
  useEffect(() => {
    if (view.city === null) update({ city: remembered }, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- update is stable in effect
  }, [view.city, remembered]);

  // Debounce the search box; typing replaces the history entry instead of adding one per pause.
  useEffect(() => {
    const v = qInput.trim();
    if (v === q) return;
    const h = setTimeout(() => update({ q: v }, true), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(h);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- update is stable in effect
  }, [qInput]);
  // Back / a shared link changes q under the box: follow it.
  // eslint-disable-next-line react-hooks/set-state-in-effect -- mirror the URL into the input
  useEffect(() => { setQInput(cur => (cur.trim() === q ? cur : q)); }, [q]);

  const mode = promosMode(view);
  const searchText = promoSearchText(q);
  const active = mode !== 'start';
  const flat = mode === 'flat';
  const pageSize = flat ? FLAT_PAGE_SIZE : PAGE_SIZE;

  const filterArgs = useMemo(() => ({
    city: city || undefined,
    chainId: chainId || undefined,
    branch: chainId ? branch ?? undefined : undefined,
    category: category || undefined,
    bands: bands.length ? bands : undefined,
    promoTypes: types.length ? types : undefined,
    q: searchText || undefined,
    endingWithinHours: endingSoon ? ENDING_SOON_HOURS : undefined,
    sort,
  }), [city, chainId, branch, category, bands, types, searchText, endingSoon, sort]);

  // Two independent queries; each section renders when its own data arrives.
  // A new key leaves the old request unused, and react-query aborts it
  // (the signal goes to axios).
  // מבצעים מקודמים: every state, the same filters minus branch and sort.
  const promotedArgs = useMemo(() => ({ ...filterArgs, branch: undefined, sort: undefined }), [filterArgs]);
  const promoted = useQuery({
    queryKey: ['promos-promoted', promotedArgs],
    queryFn: ({ signal }) => getPromotedPromos(promotedArgs, signal),
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });

  const list = useInfiniteQuery({
    queryKey: ['promos-list', mode, filterArgs],
    queryFn: ({ pageParam, signal }) =>
      (flat ? getFlatPromos : getGroupedPromos)({ ...filterArgs, limit: pageSize, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: (last: GroupedPromoItem[], all: GroupedPromoItem[][]) =>
      last.length === pageSize ? all.reduce((n, pg) => n + pg.length, 0) : undefined,
    enabled: active,
    staleTime: 60_000,
  });
  const rows = useMemo(() => list.data?.pages.flat() ?? [], [list.data]);

  // Only refresh the branch list when not already narrowed to one branch.
  useEffect(() => {
    if (mode !== 'grouped' || filterArgs.branch != null) return;
    const seen = new Map<number, string>();
    for (const r of list.data?.pages[0] ?? []) {
      if (r.store_fk != null && !seen.has(r.store_fk)) seen.set(r.store_fk, r.branch ?? String(r.store_fk));
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- options from the unfiltered-by-branch page
    setBranchOpts(Array.from(seen, ([fk, name]) => ({ fk, name })));
  }, [list.data, mode, filterArgs.branch, chainId]);

  const grouped = useMemo(() => (flat ? [] : groupRows(rows)), [rows, flat]);
  const showCityHeaders = !city;
  const catOpts = useMemo(() => categoryOptions(tree.data?.nodes ?? [], en), [tree.data, en]);
  const departments = catOpts.filter(c => c.level === 1);
  const promotedRows = promoted.data ?? [];

  const handleCityChange = (next: string) => {
    update({ city: next });
    if (next) rememberCity(next); // keep search + promos in sync
  };

  const toggle = (key: 'bands' | 'types', list: string[], v: string) =>
    update({ [key]: (list.includes(v) ? list.filter(x => x !== v) : [...list, v]).join(',') });

  const activeCount =
    bands.length + types.length + (endingSoon ? 1 : 0) + (category ? 1 : 0) +
    (branch != null ? 1 : 0) + (chainId ? 1 : 0) + (q ? 1 : 0);

  const clearAll = () => {
    setQInput('');
    update({ chain: null, branch: null, cat: null, bands: null, types: null, ending: null, q: null, sort: null });
  };

  const filterBar = (
    <div className="flex flex-col gap-3">
      {/* Row 1 — dropdowns */}
      <div className="flex flex-wrap gap-2">
        <select
          value={city}
          onChange={e => handleCityChange(e.target.value)}
          className={SELECT_CLS}
          dir="rtl"
          aria-label="עיר"
        >
          <option value="">כל הערים</option>
          {city && !cityInfos.some(c => c.city === city) && <option value={city}>{city}</option>}
          {cityInfos.map(c => <option key={c.city} value={c.city}>{c.city}</option>)}
        </select>

        <select
          value={chainId}
          onChange={e => update({ chain: e.target.value, branch: null })}
          className={SELECT_CLS}
          dir="rtl"
          aria-label="רשת"
        >
          <option value="">כל הרשתות</option>
          {chains.map(c => <option key={c.chain_id} value={c.chain_id}>{c.name}</option>)}
        </select>

        {/* SU11A-60: department / category / sub-category, indented. */}
        <select
          value={category}
          onChange={e => update({ cat: e.target.value })}
          className={clsx(SELECT_CLS, 'max-w-full')}
          dir="rtl"
          aria-label={t('promos.category_label')}
          disabled={catOpts.length === 0}
        >
          <option value="">{t('promos.all_categories')}</option>
          {catOpts.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
        </select>

        {/* Branch is only meaningful within one chain: branch names are not
            unique across chains, so offering it under "all chains" would be
            ambiguous. Disabled rather than hidden, so the control is
            discoverable and its precondition is visible. */}
        <select
          value={branch ?? ''}
          onChange={e => update({ branch: e.target.value || null })}
          className={SELECT_CLS}
          dir="rtl"
          disabled={!chainId}
          title={!chainId ? 'בחרו רשת אחת כדי לסנן לפי סניף' : undefined}
          aria-label="סניף"
        >
          <option value="">{chainId ? 'כל הסניפים' : 'סניף (בחרו רשת)'}</option>
          {chainId && branchOpts.map(b => (
            <option key={b.fk} value={b.fk}>{b.name}</option>
          ))}
        </select>

        <select
          value={sort}
          onChange={e => update({ sort: e.target.value === 'discount' ? null : e.target.value })}
          className={SELECT_CLS}
          dir="rtl"
          aria-label="מיון"
        >
          {SORTS.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </div>

      {/* Row 2 — discount bands */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-gray-500 ms-1">הנחה:</span>
        {BANDS.map(b => (
          <Chip
            key={b.value}
            label={b.label}
            active={bands.includes(b.value)}
            onClick={() => toggle('bands', bands, b.value)}
          />
        ))}
      </div>

      {/* Row 3 — promo shape + ending soon */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-gray-500 ms-1">סוג:</span>
        {PROMO_TYPES.map(pt => (
          <Chip
            key={pt.value}
            label={pt.label}
            active={types.includes(pt.value)}
            onClick={() => toggle('types', types, pt.value)}
          />
        ))}
        <span className="w-px h-4 bg-gray-200 mx-1" />
        <Chip
          label={`מסתיים ב-${ENDING_SOON_HOURS} שעות`}
          active={endingSoon}
          onClick={() => update({ ending: endingSoon ? null : '1' })}
        />
        {activeCount > 0 && (
          <button
            onClick={clearAll}
            className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-rose-600 transition-colors px-2"
          >
            <X size={12} /> נקה סינון
          </button>
        )}
      </div>
    </div>
  );

  const spinner = (
    <div className="flex justify-center items-center py-24">
      <Loader2 size={32} className="animate-spin text-emerald-500" aria-label={t('promos.loading')} />
    </div>
  );

  const retryBox = (onRetry: () => void, small = false) => (
    <div role="alert" className={clsx('flex flex-col items-center gap-2 text-gray-600', small ? 'py-3' : 'py-24')}>
      <span className="flex items-center gap-2 text-sm"><AlertCircle size={small ? 16 : 28} className="text-rose-400" aria-hidden="true" />
        {small ? t('promos.promoted_error') : 'שגיאה בטעינת המבצעים'}</span>
      <button type="button" onClick={onRetry}
        className="min-h-[44px] px-4 rounded-lg border border-gray-300 bg-white text-sm text-gray-800 hover:border-emerald-400
                   focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700">
        {t('promos.retry')}
      </button>
    </div>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-4xl mx-auto px-4 pt-8 pb-24" dir="rtl">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">🔥 מבצעים</h1>
        <p className="text-sm text-gray-500 mb-4">
          {city ? `מבצעים ב${city}, לפי רשת וסניף` : 'מבצעים בכל הערים, לפי רשת, עיר וסניף'}
        </p>

        {/* Search — always visible, above the filter panel */}
        <div className="relative mb-3">
          <Search size={15} className="absolute top-1/2 -translate-y-1/2 end-3 text-gray-500 pointer-events-none" />
          <input
            type="search"
            value={qInput}
            onChange={e => setQInput(e.target.value)}
            placeholder="חיפוש מוצר במבצעים"
            className="w-full ps-3 pe-9 py-2 border border-gray-300 rounded-lg text-sm text-gray-700
                       placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            dir="rtl"
            aria-label="חיפוש מוצר במבצעים"
            aria-describedby={q && !searchText ? 'promos-q-short' : undefined}
          />
        </div>
        {q && !searchText && (
          <p id="promos-q-short" className="-mt-2 mb-3 text-xs text-gray-600" aria-live="polite">{t('promos.search_too_short')}</p>
        )}

        {/* Mobile: collapsible panel so the list stays visible. Desktop: always open. */}
        <button
          onClick={() => setFiltersOpen(o => !o)}
          aria-expanded={filtersOpen}
          className="sm:hidden w-full flex items-center justify-between gap-2 px-3 py-2 mb-3
                     border border-gray-300 rounded-lg bg-white text-sm text-gray-700"
        >
          <span className="flex items-center gap-2">
            <SlidersHorizontal size={14} className="text-gray-500" />
            סינון ומיון
            {activeCount > 0 && (
              <span className="text-[11px] font-bold px-1.5 rounded-full bg-emerald-700 text-white">
                {activeCount}
              </span>
            )}
          </span>
          <ChevronDown size={15} className={clsx('text-gray-500 transition-transform', !filtersOpen && '-rotate-90')} />
        </button>
        <div className={clsx('mb-6', filtersOpen ? 'block' : 'hidden sm:block')}>{filterBar}</div>

        {/* Each section renders when its own data arrives. The promoted one
            shows a one-line placeholder while it loads (no jump when the
            usual empty answer comes back) and its own retry on failure. */}
        <>
            {promoted.isPending ? (
              <p className="mb-6 h-6 text-xs text-gray-500" aria-live="polite">{t('promos.promoted_loading')}</p>
            ) : promoted.isError && !promoted.data ? (
              <div className="mb-6">{retryBox(() => void promoted.refetch(), true)}</div>
            ) : promotedRows.length > 0 && (
              <section aria-labelledby="promoted-title" className="mb-6">
                <h2 id="promoted-title" className="text-base font-bold text-gray-900 mb-2">{t('promos.promoted_title')}</h2>
                <ul className="grid gap-2 sm:grid-cols-2">
                  {promotedRows.map(r => <FlatCard key={`${r.chain_id}-${r.store_fk}-${r.item_code}`} item={r} term={searchText} />)}
                </ul>
              </section>
            )}

            {!active ? (
              <section aria-labelledby="promos-start" className="bg-white rounded-xl border border-gray-200 p-5 text-center">
                <h2 id="promos-start" className="text-base font-bold text-gray-900">{t('promos.start_title')}</h2>
                <p className="text-sm text-gray-600 mt-1">{t('promos.start_text')}</p>
                {departments.length > 0 && (
                  <div className="flex flex-wrap justify-center gap-2 mt-4" role="group" aria-label={t('promos.departments')}>
                    {departments.map(d => (
                      <button
                        key={d.id}
                        type="button"
                        onClick={() => update({ cat: d.id })}
                        className="min-h-[44px] px-3 rounded-full border border-gray-300 bg-white text-sm text-gray-800
                                   hover:border-emerald-500 focus-visible:outline focus-visible:outline-2
                                   focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
                      >
                        {d.label}
                      </button>
                    ))}
                  </div>
                )}
              </section>
            ) : list.isPending ? spinner : list.isError && rows.length === 0 ? retryBox(() => void list.refetch()) : rows.length === 0 ? (
              <p className="text-center text-gray-500 py-24" dir="auto">אין מבצעים תואמים</p>
            ) : (
              <>
                <p className="text-xs text-gray-500 mb-3">{rows.length} מבצעים</p>
                {flat ? (
                  <ul className="flex flex-col gap-2">
                    {(rows as FlatPromoItem[]).map(r => (
                      <FlatCard key={`${r.chain_id}-${r.item_code}-${r.store_fk}-${r.promo_description}`} item={r} term={searchText} />
                    ))}
                  </ul>
                ) : (
                  <div className="flex flex-col gap-4">
                    {grouped.map(cg => (
                      <Collapsible key={cg.chain} title={cg.chain} count={cg.count} level="chain">
                        {cg.cities.map(cityGrp => {
                          const branches = cityGrp.branches.map(b => (
                            <Collapsible
                              key={`${cityGrp.city}-${b.branch}`}
                              title={b.branch}
                              count={b.rows.length}
                              level="branch"
                            >
                              <div className="px-1 pb-1">
                                {b.rows.map((r, i) => (
                                  <PromoRow key={`${r.item_code}-${r.store_fk}-${i}`} item={r} term={searchText} />
                                ))}
                              </div>
                            </Collapsible>
                          ));
                          return showCityHeaders ? (
                            <Collapsible key={cityGrp.city} title={cityGrp.city} level="city">
                              <div className="ps-2">{branches}</div>
                            </Collapsible>
                          ) : (
                            <div key={cityGrp.city}>{branches}</div>
                          );
                        })}
                      </Collapsible>
                    ))}
                  </div>
                )}

                {list.hasNextPage && (
                  <div className="flex justify-center mt-6">
                    <button
                      onClick={() => void list.fetchNextPage()}
                      disabled={list.isFetchingNextPage}
                      className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 bg-white
                                 text-sm text-gray-700 hover:border-emerald-400 disabled:opacity-50 transition-colors"
                    >
                      {list.isFetchingNextPage && <Loader2 size={14} className="animate-spin" />}
                      טען עוד
                    </button>
                  </div>
                )}
              </>
            )}
        </>
      </main>
    </div>
  );
}
