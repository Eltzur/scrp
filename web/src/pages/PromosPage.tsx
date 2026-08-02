import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, Loader2, AlertCircle } from 'lucide-react';
import clsx from 'clsx';
import type { GroupedPromoItem, PromoChain, CityInfo } from '../api/client';
import { getGroupedPromos, getPromoChains } from '../api/client';
import { useCities } from '../api/hooks';
import { detectCity, rememberCity } from '../utils/city';

const PAGE_SIZE = 300;

const SELECT_CLS =
  'border border-gray-300 rounded-lg text-sm text-gray-700 bg-white px-3 py-1.5 ' +
  'hover:border-emerald-400 focus:outline-none focus:ring-2 focus:ring-emerald-500';

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
 *  The endpoint already sorts chain → city → branch → discount desc, so Maps
 *  (which keep insertion order) reproduce that hierarchy without re-sorting —
 *  re-sorting here would silently break the discount ordering within a branch. */
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

function PromoRow({ item }: { item: GroupedPromoItem }) {
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
        {/* Suppressed for freebies: a gift promo has discount_price 0, so this
            would read "5 units for ₪0.00". The description carries the terms. */}
        {isBundle && !isFreebie && (
          <span className="inline-block mt-1 text-[11px] font-medium px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
            {Math.round(item.min_qty!)} יח' ב-{fmtPrice(item.discount_price ?? 0)}
          </span>
        )}
        {isFreebie && item.promo_description && (
          <p className="text-[11px] text-gray-500 mt-1" dir="auto">{item.promo_description}</p>
        )}
        {item.promo_end && (
          <p className="text-[11px] text-gray-400 mt-1">{fmtDate(item.promo_end)}</p>
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
              isFreebie ? 'text-gray-500' : 'text-gray-400 line-through',
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
          {subtitle && <span className="text-xs text-gray-400 truncate" dir="auto">{subtitle}</span>}
          {count != null && <span className="text-xs text-gray-400 shrink-0">({count})</span>}
        </span>
        <ChevronDown
          size={16}
          className={clsx('text-gray-400 shrink-0 transition-transform', !open && '-rotate-90')}
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
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error,   setError]   = useState(false);
  const [hasMore, setHasMore] = useState(false);

  useEffect(() => { getPromoChains().then(setChains).catch(() => setChains([])); }, []);

  // Resolve the active city ONCE, from the same source the search page uses, so
  // the two pages never disagree about "your city". '' means "all cities".
  const resolved = useRef(false);
  useEffect(() => {
    if (resolved.current || cityInfos.length === 0) return;
    resolved.current = true;
    detectCity(cityInfos as CityInfo[]).then(setCity);
  }, [cityInfos]);

  // (Re)fetch page 0 whenever the filters change.
  useEffect(() => {
    if (city === null) return; // wait for city resolution
    setLoading(true);
    setError(false);
    getGroupedPromos({ city: city || undefined, chainId: chainId || undefined, limit: PAGE_SIZE, offset: 0 })
      .then(data => {
        setRows(data);
        setHasMore(data.length === PAGE_SIZE);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [city, chainId]);

  const loadMore = () => {
    setLoadingMore(true);
    getGroupedPromos({
      city: city || undefined, chainId: chainId || undefined,
      limit: PAGE_SIZE, offset: rows.length,
    })
      .then(data => {
        setRows(prev => [...prev, ...data]);
        setHasMore(data.length === PAGE_SIZE);
      })
      .catch(() => setError(true))
      .finally(() => setLoadingMore(false));
  };

  const grouped = useMemo(() => groupRows(rows), [rows]);
  const showCityHeaders = !city; // only meaningful when viewing all cities

  const handleCityChange = (next: string) => {
    setCity(next);
    if (next) rememberCity(next); // keep search + promos in sync
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-4xl mx-auto px-4 pt-8 pb-24" dir="rtl">
        <h1 className="text-2xl font-bold text-gray-900 mb-1">🔥 מבצעים</h1>
        <p className="text-sm text-gray-500 mb-4">
          {city ? `מבצעים ב${city}, לפי רשת וסניף` : 'מבצעים בכל הערים, לפי רשת, עיר וסניף'}
        </p>

        <div className="flex flex-wrap gap-3 mb-6">
          <select
            value={city ?? ''}
            onChange={e => handleCityChange(e.target.value)}
            className={SELECT_CLS}
            dir="rtl"
            disabled={city === null}
          >
            <option value="">כל הערים</option>
            {cityInfos.map(c => (
              <option key={c.city} value={c.city}>{c.city}</option>
            ))}
          </select>

          <select
            value={chainId}
            onChange={e => setChainId(e.target.value)}
            className={SELECT_CLS}
            dir="rtl"
          >
            <option value="">כל הרשתות</option>
            {chains.map(c => (
              <option key={c.chain_id} value={c.chain_id}>{c.name}</option>
            ))}
          </select>

          {chainId && (
            <button
              onClick={() => setChainId('')}
              className="text-sm text-gray-400 hover:text-rose-500 transition-colors px-2"
            >
              נקה סינון
            </button>
          )}
        </div>

        {loading || city === null ? (
          <div className="flex justify-center items-center py-24">
            <Loader2 size={32} className="animate-spin text-emerald-500" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-2 py-24 text-gray-400">
            <AlertCircle size={28} className="text-rose-400" />
            <p className="text-sm">שגיאה בטעינת המבצעים</p>
          </div>
        ) : rows.length === 0 ? (
          <p className="text-center text-gray-400 py-24" dir="auto">
            {city ? `אין מבצעים ב${city} כרגע` : 'אין מבצעים זמינים כרגע'}
          </p>
        ) : (
          <>
            <p className="text-xs text-gray-400 mb-3">{rows.length} מבצעים</p>
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
                            <PromoRow key={`${r.item_code}-${i}`} item={r} />
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
