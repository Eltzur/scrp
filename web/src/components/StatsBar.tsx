import { useStats } from '../api/hooks';

export default function StatsBar() {
  const { data } = useStats();
  if (!data) return null;

  const prices = data.prices_count.toLocaleString();
  const chains = data.chains_count;
  const stores = data.stores_count;

  return (
    <p className="text-xs text-gray-400">
      Searching across{' '}
      <span className="text-gray-600 font-medium">{chains} chains</span>,{' '}
      <span className="text-gray-600 font-medium">{stores} stores</span>,{' '}
      <span className="text-gray-600 font-medium">{prices} prices</span>
    </p>
  );
}
