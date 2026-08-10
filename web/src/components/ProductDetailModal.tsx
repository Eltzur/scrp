import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { X, ImageOff, Loader2, CheckCircle2 } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import { getProductDetails, productImageUrl } from '../api/client';
import type { ProductWithPrices, PriceQuote, ProductDetails } from '../api/client';

interface Props {
  item: ProductWithPrices;
  onClose: () => void;
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

export default function ProductDetailModal({ item, onClose }: Props) {
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

        {/* Scrollable body */}
        <div className="overflow-y-auto p-4 flex flex-col gap-4">
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

          {/* Prices — always present, the reason the modal is useful without GS1 */}
          <Section title={t('product_modal.prices')}>
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
          </Section>

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

          {/* No GS1 data: a quiet note, never an error. This is the majority
              case (~92% of items), so it must not read as something broken. */}
          {!loading && !details?.has_gs1_data && (
            <p className="text-xs text-gray-500 text-center pt-1" dir="auto">
              {t('product_modal.no_extra_info')}
            </p>
          )}

          <p className="text-[11px] text-gray-500 font-mono text-center pt-1" dir="ltr">
            {barcode}
          </p>
        </div>
      </div>
    </div>,
    document.body,
  );
}
