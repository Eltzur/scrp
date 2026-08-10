import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Loader2, AlertCircle, Search, SlidersHorizontal, X } from 'lucide-react';
import clsx from 'clsx';
import type {
  GroupedPromoItem, PromoChain, CityInfo, PromoShape, PromoSort,
} from '../api/client';
import { getGroupedPromos, getPromoChains } from '../api/client';
import { useCities } from '../api/hooks';
import { detectCity, rememberCity } from '../utils/city';

const PAGE_SIZE = 300;
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
const PROMO_TYPES: { value: PromoShape; label: string }[] = [
  { value: 'gift',     label: '1+1 / מתנה'    },
  { value: 'bundle',   label: "כמה יח' ב-₪"   },
  { value: 'fixed',    label: 'מחיר מבצע'     },
  { value: 'discount', label: '% הנחה'        },
  { value: 'basket',   label: 'בתנאי / מעל סכום' },
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

/** Basket promos: conditional / spend-threshold deals with no per-unit price.
 *  Deliberately a different shape from a unit card — no struck-through shelf
 *  price, no unit price, no % badge, because none of those exist for these
 *  rows and inventing them is exactly the bug this whole workstream fixed. */
function BasketCard({ item }: { item: GroupedPromoItem }) {
  const hasThreshold = item.min_purchase_amount != null && item.min_purchase_amount > 0;
  return (
    <div className="flex items-start justify-between gap-3 px-3 py-2.5 border-t border-gray-100 first:border-t-0 bg-sky-50/30">
      <div className="min-w-0 flex-1">
        {/* Description leads here: for these rows it carries the actual terms
            (common for weighted goods — fish, meat, produce). */}
        <p className="text-sm text-gray-900 leading-snug font-medium" dir="auto">
          {item.promo_description ?? item.product_name ?? item.item_code}
        </p>
        {item.product_name && item.promo_description && (
          <p className="text-[11px] text-gray-500 mt-0.5" dir="auto">{item.product_name}</p>
        )}
        {item.promo_end && (
          <p className="text-[11px] text-gray-500 mt-1">{fmtDate(item.promo_end)}</p>
        )}
      </div>
      <div className="flex flex-col items-end gap-1 shrink-0">
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

function PromoRow({ item }: { item: GroupedPromoItem }) {
  if (item.promo_kind === 'basket') return <BasketCard item={item} />;

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
          {item.product_name ?? item.promo_description ?? item.item_code}
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

export default function PromosPage() {
  const { data: cityInfos = [] } = useCities();

  const [chains,  setChains]  = useState<PromoChain[]>([]);
  const [rows,    setRows]    = useState<GroupedPromoItem[]>([]);
  const [city,    setCity]    = useState<string | null>(null); // null = not resolved yet
  const [chainId, setChainId] = useState('');
  const [branch,  setBranch]  = useState<number | null>(null);
  const [bands,   setBands]   = useState<string[]>([]);
  const [types,   setTypes]   = useState<PromoShape[]>([]);
  const [sort,    setSort]    = useState<PromoSort>('discount');
  const [endingSoon, setEndingSoon] = useState(false);
  const [qInput,  setQInput]  = useState('');
  const [q,       setQ]       = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error,   setError]   = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [filtersOpen, setFiltersOpen] = useState(false); // mobile panel

  // Branch options are captured from an UNFILTERED-by-branch result and kept in
  // their own state. Deriving them from `rows` directly would collapse the list
  // to the single selected branch the moment one is chosen.
  const [branchOpts, setBranchOpts] = useState<{ fk: number; name: string }[]>([]);

  useEffect(() => { getPromoChains().then(setChains).catch(() => setChains([])); }, []);

  // Resolve the active city ONCE, from the same source the search page uses, so
  // the two pages never disagree about "your city". '' means "all cities".
  const resolved = useRef(false);
  useEffect(() => {
    if (resolved.current || cityInfos.length === 0) return;
    resolved.current = true;
    detectCity(cityInfos as CityInfo[]).then(setCity);
  }, [cityInfos]);

  // Debounce the search box so typing does not fire a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setQ(qInput.trim()), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [qInput]);

  // A branch belongs to exactly one chain, so any chain change invalidates it.
  useEffect(() => { setBranch(null); }, [chainId]);

  const filterArgs = useMemo(() => ({
    city: city || undefined,
    chainId: chainId || undefined,
    branch: branch ?? undefined,
    bands: bands.length ? bands : undefined,
    promoTypes: types.length ? types : undefined,
    q: q || undefined,
    endingWithinHours: endingSoon ? ENDING_SOON_HOURS : undefined,
    sort,
  }), [city, chainId, branch, bands, types, q, endingSoon, sort]);

  useEffect(() => {
    if (city === null) return; // wait for city resolution
    setLoading(true);
    setError(false);
    getGroupedPromos({ ...filterArgs, limit: PAGE_SIZE, offset: 0 })
      .then(data => {
        setRows(data);
        setHasMore(data.length === PAGE_SIZE);
        // Only refresh the branch list when not already narrowed to one branch.
        if (branch == null) {
          const seen = new Map<number, string>();
          for (const r of data) {
            if (r.store_fk != null && !seen.has(r.store_fk)) {
              seen.set(r.store_fk, r.branch ?? String(r.store_fk));
            }
          }
          setBranchOpts(Array.from(seen, ([fk, name]) => ({ fk, name })));
        }
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [filterArgs, city, branch]);

  const loadMore = () => {
    setLoadingMore(true);
    getGroupedPromos({ ...filterArgs, limit: PAGE_SIZE, offset: rows.length })
      .then(data => {
        setRows(prev => [...prev, ...data]);
        setHasMore(data.length === PAGE_SIZE);
      })
      .catch(() => setError(true))
      .finally(() => setLoadingMore(false));
  };

  const grouped = useMemo(() => groupRows(rows), [rows]);
  const showCityHeaders = !city;

  const handleCityChange = (next: string) => {
    setCity(next);
    if (next) rememberCity(next); // keep search + promos in sync
  };

  const toggle = <T extends string>(list: T[], v: T, set: (x: T[]) => void) =>
    set(list.includes(v) ? list.filter(x => x !== v) : [...list, v]);

  const activeCount =
    bands.length + types.length + (endingSoon ? 1 : 0) +
    (branch != null ? 1 : 0) + (chainId ? 1 : 0) + (q ? 1 : 0);

  const clearAll = () => {
    setChainId(''); setBranch(null); setBands([]); setTypes([]);
    setEndingSoon(false); setQInput(''); setQ(''); setSort('discount');
  };

  const filterBar = (
    <div className="flex flex-col gap-3">
      {/* Row 1 — dropdowns */}
      <div className="flex flex-wrap gap-2">
        <select
          value={city ?? ''}
          onChange={e => handleCityChange(e.target.value)}
          className={SELECT_CLS}
          dir="rtl"
          disabled={city === null}
          aria-label="עיר"
        >
          <option value="">כל הערים</option>
          {cityInfos.map(c => <option key={c.city} value={c.city}>{c.city}</option>)}
        </select>

        <select
          value={chainId}
          onChange={e => setChainId(e.target.value)}
          className={SELECT_CLS}
          dir="rtl"
          aria-label="רשת"
        >
          <option value="">כל הרשתות</option>
          {chains.map(c => <option key={c.chain_id} value={c.chain_id}>{c.name}</option>)}
        </select>

        {/* Branch is only meaningful within one chain: branch names are not
            unique across chains, so offering it under "all chains" would be
            ambiguous. Disabled rather than hidden, so the control is
            discoverable and its precondition is visible. */}
        <select
          value={branch ?? ''}
          onChange={e => setBranch(e.target.value ? Number(e.target.value) : null)}
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
          onChange={e => setSort(e.target.value as PromoSort)}
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
            onClick={() => toggle(bands, b.value, setBands)}
          />
        ))}
      </div>

      {/* Row 3 — promo shape + ending soon */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-gray-500 ms-1">סוג:</span>
        {PROMO_TYPES.map(t => (
          <Chip
            key={t.value}
            label={t.label}
            active={types.includes(t.value)}
            onClick={() => toggle(types, t.value, setTypes)}
          />
        ))}
        <span className="w-px h-4 bg-gray-200 mx-1" />
        <Chip
          label={`מסתיים ב-${ENDING_SOON_HOURS} שעות`}
          active={endingSoon}
          onClick={() => setEndingSoon(v => !v)}
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
            type="text"
            value={qInput}
            onChange={e => setQInput(e.target.value)}
            placeholder="חיפוש מוצר במבצעים"
            className="w-full ps-3 pe-9 py-2 border border-gray-300 rounded-lg text-sm text-gray-700
                       placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            dir="rtl"
            aria-label="חיפוש מוצר במבצעים"
          />
        </div>

        {/* Mobile: collapsible panel so the list stays visible. Desktop: always open. */}
        <button
          onClick={() => setFiltersOpen(o => !o)}
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

        {loading || city === null ? (
          <div className="flex justify-center items-center py-24">
            <Loader2 size={32} className="animate-spin text-emerald-500" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-2 py-24 text-gray-500">
            <AlertCircle size={28} className="text-rose-400" />
            <p className="text-sm">שגיאה בטעינת המבצעים</p>
          </div>
        ) : rows.length === 0 ? (
          <p className="text-center text-gray-500 py-24" dir="auto">
            {activeCount > 0
              ? 'אין מבצעים תואמים'
              : city ? `אין מבצעים ב${city} כרגע` : 'אין מבצעים זמינים כרגע'}
          </p>
        ) : (
          <>
            <p className="text-xs text-gray-500 mb-3">{rows.length} מבצעים</p>
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
                            <PromoRow key={`${r.item_code}-${r.store_fk}-${i}`} item={r} />
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

            {hasMore && (
              <div className="flex justify-center mt-6">
                <button
                  onClick={loadMore}
                  disabled={loadingMore}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-300 bg-white
                             text-sm text-gray-700 hover:border-emerald-400 disabled:opacity-50 transition-colors"
                >
                  {loadingMore && <Loader2 size={14} className="animate-spin" />}
                  טען עוד
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
