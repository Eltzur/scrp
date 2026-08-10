import type { BasketCompareResponse } from '../api/client';
import type { BasketEntry } from './BasketContext';

interface Props {
  result: BasketCompareResponse;
  basketItems: BasketEntry[];
}

const fmt = (n: number) =>
  new Intl.NumberFormat('he-IL', { style: 'currency', currency: 'ILS', minimumFractionDigits: 2 }).format(n);

export default function BasketResults({ result, basketItems }: Props) {
  const { chains, winner_chain_id } = result;

  if (chains.length === 0) {
    return <p className="p-6 text-sm text-gray-500 text-center">לא נמצאו מחירים לפריטי הסל</p>;
  }

  // Build lookup: chain_id → (item_code → breakdown)
  const byChain = new Map(
    chains.map(c => [c.chain_id, new Map(c.breakdown.map(b => [b.item_code, b]))])
  );

  // Cheapest found price per item across all chains
  const cheapestPerItem = new Map<string, number>();
  for (const item of basketItems) {
    const prices = chains
      .map(c => byChain.get(c.chain_id)?.get(item.item_code))
      .filter(b => b?.found && b.price != null)
      .map(b => b!.price!);
    if (prices.length) cheapestPerItem.set(item.item_code, Math.min(...prices));
  }

  const maxTotal = Math.max(...chains.map(c => c.total_price));
  const winner   = chains.find(c => c.chain_id === winner_chain_id);
  const savings  = winner ? maxTotal - winner.total_price : 0;

  return (
    <div className="p-4 space-y-3" dir="rtl">
      {/* Savings banner */}
      {savings > 0.05 && chains.length > 1 && (
        <div className="p-2.5 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-700 text-center font-medium">
          חיסכון של {fmt(savings)} לעומת הרשת היקרה ביותר
        </div>
      )}

      {/* Comparison table */}
      <div className="overflow-x-auto rounded-xl border border-gray-200">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="py-2.5 px-3 text-right text-gray-500 font-medium min-w-[130px] sticky right-0 bg-gray-50 border-l border-gray-200">
                מוצר
              </th>
              {chains.map(c => (
                <th
                  key={c.chain_id}
                  className={`py-2.5 px-3 text-center font-semibold min-w-[90px]
                    ${c.chain_id === winner_chain_id ? 'text-emerald-700 bg-emerald-50' : 'text-gray-700'}`}
                >
                  {c.chain_id === winner_chain_id && <span className="block text-base leading-none mb-0.5">🏆</span>}
                  <span>{c.chain_name ?? c.chain_id}</span>
                  <span className="block text-gray-500 font-normal mt-0.5">
                    {c.items_found}/{basketItems.length}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {basketItems.map((item, rowIdx) => {
              const cheapest = cheapestPerItem.get(item.item_code);
              return (
                <tr
                  key={item.item_code}
                  className={`border-b border-gray-100 ${rowIdx % 2 === 0 ? 'bg-white' : 'bg-gray-50/50'}`}
                >
                  <td className="py-2 px-3 text-right sticky right-0 bg-inherit border-l border-gray-200">
                    <p className="font-medium text-gray-800 truncate max-w-[130px]" dir="auto">
                      {item.item_name || item.item_code}
                    </p>
                    {item.is_weighted && (
                      <p className="text-gray-500 font-mono" dir="ltr">{item.quantity}g</p>
                    )}
                    {!item.is_weighted && item.quantity > 1 && (
                      <p className="text-gray-500">×{item.quantity}</p>
                    )}
                  </td>
                  {chains.map(c => {
                    const b = byChain.get(c.chain_id)?.get(item.item_code);
                    const isCheapest = b?.found && b.price != null && b.price === cheapest;
                    return (
                      <td
                        key={c.chain_id}
                        className={`py-2 px-3 text-center
                          ${isCheapest ? 'bg-emerald-50 text-emerald-700 font-semibold' : ''}
                          ${!b?.found ? 'text-gray-500' : 'text-gray-800'}`}
                        dir="ltr"
                      >
                        {b?.found && b.subtotal != null ? fmt(b.subtotal) : '—'}
                      </td>
                    );
                  })}
                </tr>
              );
            })}

            {/* Total row */}
            <tr className="border-t-2 border-gray-300 font-semibold">
              <td className="py-2.5 px-3 text-right text-gray-700 sticky right-0 bg-white border-l border-gray-200">
                סה&quot;כ
              </td>
              {chains.map(c => (
                <td
                  key={c.chain_id}
                  className={`py-2.5 px-3 text-center text-sm
                    ${c.chain_id === winner_chain_id
                      ? 'text-emerald-700 bg-emerald-50'
                      : 'text-gray-800'}`}
                  dir="ltr"
                >
                  {fmt(c.total_price)}
                  {c.items_missing > 0 && (
                    <span className="block text-gray-500 font-normal text-xs mt-0.5">
                      ({c.items_missing} חסרים)
                    </span>
                  )}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {chains.some(c => c.items_missing > 0) && (
        <p className="text-xs text-gray-500 text-center">— = פריט לא נמצא ברשת זו</p>
      )}
    </div>
  );
}
