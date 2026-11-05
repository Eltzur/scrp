import { useEffect, useId, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { FALLBACK_CITY, rememberedCity } from '../../utils/city';
import { getCitiesA, getPromoChainsA, searchPromos, type PromoHit } from '../api';
import { viewFromHash } from '../nav';
import { Button, ErrorBox, Loading } from '../ui';
import CurationList from './promos/CurationList';
import { HideForm, PinForm } from './promos/CurateForms';
import PromoCard from './promos/PromoCard';
import { INPUT, K } from './promos/shared';

/**
 * מבצעים (SU11A-58): search a promotion (text, barcode, promotion id, chain),
 * preview it as a card, then קידום (rank, dates, sponsored) or הסתרה (reason);
 * lists of active pins (reorder with up / down), active hides and expired rows.
 * Pins and hides change the promo lists only, never a price. Every write is
 * confirmed first and recorded in the audit log.
 *
 * SU11A-62: search results rank by relevance with the best-matching product as
 * the example; search hits and pins show where they are visible ("מוצג ב-N
 * ערים") and warn against the check city. The console runs on its own origin,
 * so the shop's remembered city is rarely available here: the check city is
 * the admin's own choice (kept in this browser), else the shop's, else Tel Aviv.
 */
const CHECK_CITY_KEY = 'xxl_admin_check_city';

function initialCheckCity(): string {
  try {
    return localStorage.getItem(CHECK_CITY_KEY) || rememberedCity() || FALLBACK_CITY;
  } catch {
    return FALLBACK_CITY;
  }
}
const VIEWS = ['search', 'pins', 'hides', 'expired'] as const;
type View = typeof VIEWS[number];

function useDebounced(v: string, ms = 350) {
  const [d, setD] = useState(v);
  useEffect(() => {
    const h = setTimeout(() => setD(v), ms);
    return () => clearTimeout(h);
  }, [v, ms]);
  return d;
}

function Hit({ h, term, checkCity }: { h: PromoHit; term: string; checkCity: string }) {
  const { t } = useTranslation();
  const [form, setForm] = useState<'pin' | 'hide' | null>(null);
  const c = h.curation;
  // A hidden promotion shows nowhere, whatever its rows: no coverage line.
  const p = c.hide_id != null ? { ...h, cities: undefined } : h;
  return (
    <li>
      <PromoCard p={p} term={term} matches={h.matches} checkCity={checkCity}>
        {(c.pin_rank != null || c.hide_id != null) && (
          <p className="mt-2 text-xs font-semibold text-emerald-900">
            {c.pin_rank != null ? t(`${K}.card.pinned_at`, { rank: c.pin_rank }) : t(`${K}.card.hidden`)}
          </p>
        )}
        {form === null ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <Button tone="primary" onClick={() => setForm('pin')} disabled={!h.live || c.pin_id != null || c.hide_id != null}>
              {t(`${K}.pin`)}
            </Button>
            <Button tone="danger" onClick={() => setForm('hide')} disabled={c.pin_id != null || c.hide_id != null}>
              {t(`${K}.hide`)}
            </Button>
          </div>
        ) : form === 'pin' ? <PinForm p={h} onDone={() => setForm(null)} />
          : <HideForm p={h} onDone={() => setForm(null)} />}
      </PromoCard>
    </li>
  );
}

function SearchView({ checkCity }: { checkCity: string }) {
  const { t } = useTranslation();
  const id = useId();
  const [text, setText] = useState('');
  const [chain, setChain] = useState('');
  const [activeOnly, setActiveOnly] = useState(true);
  const q = useDebounced(text.trim());
  const chains = useQuery({ queryKey: ['admin', 'promo-chains'], queryFn: getPromoChainsA, staleTime: 3600_000, retry: 0 });
  const enabled = q.length >= 2 || chain !== '';
  const r = useQuery({
    queryKey: ['admin', 'promo-search', q, chain, activeOnly],
    queryFn: () => searchPromos({ q: q || undefined, chain: chain || undefined, active_only: activeOnly }),
    enabled, retry: 0,
  });
  return (
    <div>
      <label htmlFor={`${id}-q`} className="block text-sm font-semibold text-gray-800 mb-1">{t(`${K}.search_label`)}</label>
      <div className="relative">
        <Search size={16} className="absolute top-1/2 -translate-y-1/2 start-3 text-gray-500 pointer-events-none" aria-hidden="true" />
        <input id={`${id}-q`} type="search" value={text} onChange={e => setText(e.target.value)} dir="auto" autoComplete="off"
          placeholder={t(`${K}.search_placeholder`)} aria-describedby={`${id}-hint`} className={`${INPUT} ps-9`} />
      </div>
      <p id={`${id}-hint`} className="text-xs text-gray-500 mt-1">{t(`${K}.search_hint`)}</p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="min-w-[12rem]">
          <label htmlFor={`${id}-c`} className="block text-sm font-semibold text-gray-800 mb-1">{t(`${K}.chain_label`)}</label>
          <select id={`${id}-c`} value={chain} onChange={e => setChain(e.target.value)} className={INPUT}>
            <option value="">—</option>
            {(chains.data ?? []).map(c => <option key={c.chain_id} value={c.chain_id}>{c.name}</option>)}
          </select>
        </div>
        <label className="flex items-center gap-2 min-h-[44px] text-sm text-gray-900">
          <input type="checkbox" checked={activeOnly} onChange={e => setActiveOnly(e.target.checked)} className="w-5 h-5 accent-emerald-700" />
          {t(`${K}.active_only`)}
        </label>
      </div>
      <div className="mt-4">
        {!enabled ? null : r.isPending ? <Loading /> : r.isError ? <ErrorBox error={r.error} onRetry={() => void r.refetch()} />
          : r.data.items.length === 0 ? <p className="text-sm text-gray-700 py-4">{t(`${K}.no_results`)}</p>
            : <ul className="space-y-3">{r.data.items.map(h => (
              <Hit key={`${h.chain_id}:${h.promo_id}`} h={h} term={q} checkCity={checkCity} />))}</ul>}
      </div>
    </div>
  );
}

export default function PromosScreen() {
  const { t } = useTranslation();
  const [view, setView] = useState<View>(() => viewFromHash(VIEWS, 'search'));
  const id = useId();
  const [checkCity, setCheckCity] = useState(initialCheckCity);
  const cities = useQuery({ queryKey: ['admin', 'cities'], queryFn: getCitiesA, staleTime: 3600_000, retry: 0 });
  const pickCity = (c: string) => {
    setCheckCity(c);
    try { localStorage.setItem(CHECK_CITY_KEY, c); } catch { /* private mode: this session only */ }
  };
  const cityOpts = cities.data ?? [];
  return (
    <div>
      <p className="text-sm text-gray-700 mb-4">{t(`${K}.intro`)}</p>
      <div className="mb-4 max-w-sm">
        <label htmlFor={`${id}-city`} className="block text-sm font-semibold text-gray-800 mb-1">{t(`${K}.check_city`)}</label>
        <select id={`${id}-city`} value={checkCity} onChange={e => pickCity(e.target.value)} className={INPUT}
          aria-describedby={`${id}-city-hint`} dir="rtl">
          {!cityOpts.includes(checkCity) && <option value={checkCity}>{checkCity}</option>}
          {cityOpts.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <p id={`${id}-city-hint`} className="text-xs text-gray-600 mt-1">{t(`${K}.check_city_hint`)}</p>
      </div>
      <div role="tablist" aria-label={t(`${K}.tabs.label`)} className="flex gap-1 overflow-x-auto mb-4 -mx-1 px-1">
        {VIEWS.map(v => (
          <button
            key={v}
            type="button"
            role="tab"
            aria-selected={view === v}
            onClick={() => setView(v)}
            className={`shrink-0 min-h-[44px] px-3 rounded-full text-sm font-semibold border
              focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700
              ${view === v ? 'bg-emerald-700 text-white border-emerald-700' : 'bg-white text-gray-800 border-gray-300 hover:bg-gray-50'}`}
          >
            {t(`${K}.tabs.${v}`)}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {view === 'search' ? <SearchView checkCity={checkCity} /> : <CurationList key={view} view={view} checkCity={checkCity} />}
      </div>
    </div>
  );
}
