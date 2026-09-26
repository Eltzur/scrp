import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, ImageOff, Loader2, CheckCircle2 } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { getProductDetails, productImageUrl } from '../api/client';
import ReviewsPanel from './ReviewsPanel';
import type { ProductWithPrices, PriceQuote, ProductDetails } from '../api/client';

interface Props {
  item: ProductWithPrices;
  onClose: () => void;
  /** Which tab to open on. Defaults to prices. */
  initialTab?: 'prices' | 'info' | 'reviews';
}

function cheapestPerChain(quotes: PriceQuote[]): PriceQuote[] {
  const byChain = new Map<string, PriceQuote>();
  for (const q of quotes) {
    const existing = byChain.get(q.chain_id);
    if (!existing || q.price < existing.price) byChain.set(q.chain_id, q);
  }
  return Array.from(byChain.values()).sort((a, b) => a.price - b.price);
}

/** Section wrapper — renders nothing at all when it has no content, so a
 *  product with partial GS1 data shows a short modal rather than a run of
 *  empty headings. */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  if (!children) return null;
  return (
    <section className="border-t border-gray-100 pt-4">
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">{title}</h4>
      {children}
    </section>
  );
}

function Chip({ label, tone = 'gray' }: { label: string; tone?: 'gray' | 'amber' | 'rose' }) {
  return (
    <span
      className={clsx(
        'inline-block text-xs font-medium px-2 py-0.5 rounded-full border',
        tone === 'gray'  && 'bg-gray-50 text-gray-700 border-gray-200',
        tone === 'amber' && 'bg-amber-50 text-amber-800 border-amber-200',
        tone === 'rose'  && 'bg-rose-50 text-rose-700 border-rose-200',
      )}
      dir="auto"
    >
      {label}
    </span>
  );
}

export type ModalTab = 'prices' | 'info' | 'reviews';

// 'מחירים' already exists as product_modal.prices — reused rather than adding
// a duplicate key that could drift from it.
const TAB_LABEL_KEY: Record<ModalTab, string> = {
  prices:  'product_modal.prices',
  info:    'ratings.tab_info',
  reviews: 'ratings.tab_reviews',
};

export default function ProductDetailModal({ item, onClose, initialTab = 'prices' }: Props) {
  const [tab, setTab] = useState<ModalTab>(initialTab);
  // Roving focus for the tablist: ArrowLeft/Right move between tabs and move
  // focus with the selection, per the WAI-ARIA tabs pattern. RTL is handled by
  // treating the arrows as "previous/next" rather than literal directions.
  const tabRefs = useRef<Record<ModalTab, HTMLButtonElement | null>>({ prices: null, info: null, reviews: null });
  const ORDER: ModalTab[] = ['prices', 'info', 'reviews'];
  const onTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft' && e.key !== 'Home' && e.key !== 'End') return;
    e.preventDefault();
    const i = ORDER.indexOf(tab);
    let next: ModalTab;
    if (e.key === 'Home') next = ORDER[0];
    else if (e.key === 'End') next = ORDER[ORDER.length - 1];
    else {
      // In RTL, ArrowLeft advances visually forward; ArrowRight goes back.
      const delta = e.key === 'ArrowLeft' ? 1 : -1;
      next = ORDER[(i + delta + ORDER.length) % ORDER.length];
    }
    setTab(next);
    tabRefs.current[next]?.focus();
  };
  const { t, i18n } = useTranslation();
  const [details, setDetails] = useState<ProductDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [imageBroken, setImageBroken] = useState(false);

  const { product } = item;
  const barcode = product.item_code;
  const quotes = cheapestPerChain(item.quotes);

  const displayName =
    product.canonical_name ||
    Object.values(product.names_per_chain ?? {})[0] ||
    barcode;

  const fmtPrice = (n: number) =>
    new Intl.NumberFormat(i18n.language, {
      style: 'currency', currency: 'ILS', minimumFractionDigits: 2,
    }).format(n);

  // Escape to close, and lock body scroll while open. Restoring the previous
  // overflow value rather than clearing it keeps this safe if another overlay
  // (e.g. the basket drawer) is already holding the lock.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  // A failed details call is NOT surfaced as an error: the enrichment is
  // supplementary, and the name/price view below is still fully useful.
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getProductDetails(barcode)
      .then(d => { if (!cancelled) setDetails(d); })
      .catch(() => { if (!cancelled) setDetails(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [barcode]);

  const hasImage = details?.has_image && !imageBroken;
  const k = details?.kashrut;
  const kashrutChips = k
    ? [
        k.supervision_type,
        ...k.rabbinate,
        ...k.board,
        k.kosher_for_passover,
        k.israel_milk,
        k.cooking_israel,
        k.sabbath_observing,
        k.sheviit_orlah_tevel,
      ].filter((v): v is string => !!v)
    : [];

  return createPortal(
    <div
      className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-label={displayName}
    >
      {/* Dimmed backdrop — click to close */}
      <div className="absolute inset-0 bg-black/50 backdrop-blur-[2px]" onClick={onClose} />

      {/* Bottom sheet on mobile, centered card from sm up */}
      <div
        className="relative w-full sm:max-w-lg max-h-[92vh] sm:max-h-[88vh] bg-white
                   rounded-t-2xl sm:rounded-2xl shadow-2xl flex flex-col overflow-hidden"
        dir="rtl"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 p-4 border-b border-gray-100">
          <div className="min-w-0">
            <h3 className="font-semibold text-gray-900 text-base leading-snug" dir="auto">
              {displayName}
            </h3>
            {(details?.brand || product.manufacturer) && (
              <p className="text-xs text-gray-500 mt-0.5" dir="auto">
                {details?.brand || product.manufacturer}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="shrink-0 p-1.5 rounded-lg text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
            aria-label={t('product_modal.close')}
          >
            <X size={18} />
          </button>
        </div>

        {/* Shared context: identifies the product on every tab, so it is
            deliberately OUTSIDE all three tabpanels. */}
        <div className="px-4 pt-4 flex flex-col gap-2">
          {/* Image or placeholder */}
          <div className="flex justify-center">
            {loading ? (
              <div className="w-40 h-40 rounded-xl bg-gray-50 flex items-center justify-center">
                <Loader2 size={22} className="animate-spin text-gray-500" />
              </div>
            ) : hasImage ? (
              <img
                src={productImageUrl(barcode)}
                alt={displayName}
                loading="lazy"
                onError={() => setImageBroken(true)}
                className="w-40 h-40 object-contain rounded-xl bg-white border border-gray-100"
              />
            ) : (
              <div className="w-40 h-40 rounded-xl bg-gray-50 border border-dashed border-gray-200 flex flex-col items-center justify-center gap-1.5 text-gray-500">
                <ImageOff size={26} />
                <span className="text-[11px] text-gray-500">{t('product_modal.no_image')}</span>
              </div>
            )}
          </div>
          <p className="text-[11px] text-gray-500 font-mono text-center pt-1" dir="ltr">
            {barcode}
          </p>
        </div>

        {/* Tabs */}
        <div
          role="tablist"
          aria-label={t('ratings.title')}
          className="flex border-b border-gray-100 px-2"
        >
          {ORDER.map(id => {
            const selected = tab === id;
            return (
              <button
                key={id}
                ref={el => { tabRefs.current[id] = el; }}
                role="tab"
                id={`tab-${id}`}
                aria-selected={selected}
                aria-controls={`panel-${id}`}
                tabIndex={selected ? 0 : -1}
                onClick={() => setTab(id)}
                onKeyDown={onTabKeyDown}
                className={clsx(
                  'px-4 py-2.5 text-sm font-semibold border-b-2 -mb-px transition-colors',
                  'focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-inset rounded-t',
                  selected
                    ? 'border-emerald-700 text-emerald-700'
                    : 'border-transparent text-gray-500 hover:text-gray-700',
                )}
              >
                {t(TAB_LABEL_KEY[id])}
              </button>
            );
          })}
        </div>

        {/* Exactly one panel is mounted at a time.
            Conditional rendering, NOT hidden={tab !== id}: the previous version
            used the attribute on a panel whose className included `flex`, and
            Tailwind's `.flex { display: flex }` is a class selector, so it beat
            the UA stylesheet's `[hidden] { display: none }`. The attribute was
            set and did nothing, which is why prices and GS1 data showed on every
            tab. Unmounting cannot be overridden by CSS. */}
        {tab === 'prices' && (
          <div
            role="tabpanel"
            id="panel-prices"
            aria-labelledby="tab-prices"
            tabIndex={0}
            className="overflow-y-auto p-4 flex flex-col gap-4"
          >
            {/* Prices — the reason the modal is useful for the ~92% of items
                with no GS1 record at all. No Section heading: the tab is the heading. */}
            <div className="divide-y divide-gray-100 rounded-lg border border-gray-100 overflow-hidden">
              {quotes.map((q, i) => {
                const isCheapest = i === 0 && quotes.length > 1;
                return (
                  <div
                    key={`${q.chain_id}-${q.store_id}`}
                    className={clsx(
                      'flex items-center justify-between px-3 py-2 text-sm',
                      isCheapest ? 'bg-emerald-50' : 'bg-white',
                    )}
                  >
                    <div className="flex items-center gap-1.5 min-w-0">
                      {isCheapest && <CheckCircle2 size={12} className="text-emerald-700 shrink-0" />}
                      <span className={clsx('font-medium truncate', isCheapest ? 'text-emerald-800' : 'text-gray-700')}>
                        {q.chain_name ?? q.chain_id}
                      </span>
                      {q.city && <span className="text-gray-500 text-xs truncate" dir="auto">· {q.city}</span>}
                    </div>
                    <span
                      className={clsx('font-semibold shrink-0 ms-2', isCheapest ? 'text-emerald-700' : 'text-gray-800')}
                      dir="ltr"
                    >
                      {fmtPrice(q.price)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {tab === 'info' && (
          <div
            role="tabpanel"
            id="panel-info"
            aria-labelledby="tab-info"
            tabIndex={0}
            className="overflow-y-auto p-4 flex flex-col gap-4"
          >
            {loading && (
              <div className="flex justify-center py-2">
                <Loader2 size={18} className="animate-spin text-gray-500" />
              </div>
            )}

            {/* Kashrut */}
            {!loading && kashrutChips.length > 0 && (
              <Section title={t('product_modal.kashrut')}>
                <div className="flex flex-wrap gap-1.5">
                  {kashrutChips.map((v, idx) => <Chip key={`${v}-${idx}`} label={v} />)}
                </div>
                {k?.passover_remark && (
                  <p className="text-xs text-gray-500 mt-2" dir="auto">{k.passover_remark}</p>
                )}
              </Section>
            )}

            {/* Nutrition */}
            {!loading && details?.nutrition && details.nutrition.rows.length > 0 && (
              <Section
                title={
                  details.nutrition.basis
                    ? `${t('product_modal.nutrition')} · ${details.nutrition.basis}`
                    : t('product_modal.nutrition')
                }
              >
                <div className="rounded-lg border border-gray-100 overflow-hidden">
                  {details.nutrition.rows.map((r, idx) => (
                    <div
                      key={`${r.label}-${idx}`}
                      className={clsx(
                        'flex items-center justify-between gap-3 px-3 py-1.5 text-sm',
                        idx % 2 ? 'bg-white' : 'bg-gray-50/60',
                      )}
                    >
                      <span className="text-gray-600 min-w-0" dir="auto">{r.label}</span>
                      <span className="font-medium text-gray-900 shrink-0" dir="auto">
                        {/* `text` first: it is the only field that renders GS1's
                            non-numeric declarations correctly. */}
                        {r.text ?? [r.value, r.uom].filter(Boolean).join(' ')}
                      </span>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* Ingredients */}
            {!loading && details?.ingredients && (
              <Section title={t('product_modal.ingredients')}>
                <p className="text-sm text-gray-700 leading-relaxed" dir="auto">{details.ingredients}</p>
              </Section>
            )}

            {/* Allergens */}
            {!loading && details?.allergens && (
              <Section title={t('product_modal.allergens')}>
                <div className="flex flex-col gap-2">
                  {details.allergens.contains.length > 0 && (
                    <div>
                      <p className="text-xs text-gray-500 mb-1">{t('product_modal.allergens_contains')}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {details.allergens.contains.map(a => <Chip key={a} label={a} tone="rose" />)}
                      </div>
                    </div>
                  )}
                  {details.allergens.may_contain.length > 0 && (
                    <div>
                      <p className="text-xs text-gray-500 mb-1">{t('product_modal.allergens_may_contain')}</p>
                      <div className="flex flex-wrap gap-1.5">
                        {details.allergens.may_contain.map(a => <Chip key={a} label={a} tone="amber" />)}
                      </div>
                    </div>
                  )}
                </div>
              </Section>
            )}

            {/* Warning labels — Israel's mandated front-of-pack marking.
                The server filters the "no marking" sentinel and the positive
                green label, so anything present here is a real warning and is
                safe to render in a warning tone. Self-hides otherwise. */}
            {!loading && details?.warning_labels && details.warning_labels.length > 0 && (
              <Section title={t('product_modal.warnings')}>
                <div className="flex flex-wrap gap-1.5">
                  {details.warning_labels.map(w => <Chip key={w} label={w} tone="rose" />)}
                </div>
              </Section>
            )}

            {/* Unit-price basis — one line, no heading furniture. */}
            {!loading && details?.unit_price_basis && (
              <Section title={t('product_modal.unit_price_basis')}>
                <p className="text-sm text-gray-700" dir="auto">{details.unit_price_basis}</p>
              </Section>
            )}

            {/* No GS1 data: a quiet note, never an error. This is the majority
                case (~92% of items), so it must not read as something broken. */}
            {!loading && !details?.has_gs1_data && (
              <p className="text-xs text-gray-500 text-center pt-1" dir="auto">
                {t('product_modal.no_extra_info')}
              </p>
            )}
          </div>
        )}

        {tab === 'reviews' && (
          <div
            role="tabpanel"
            id="panel-reviews"
            aria-labelledby="tab-reviews"
            tabIndex={0}
            className="overflow-y-auto p-4"
          >
            <ReviewsPanel itemCode={product.item_code} />
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
