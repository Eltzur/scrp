import { useTranslation } from 'react-i18next';
import { useStats } from '../api/hooks';

export default function StatsBar() {
  const { t, i18n } = useTranslation();
  const { data } = useStats();
  if (!data) return null;

  const fmt = (n: number) => n.toLocaleString(i18n.language);

  return (
    <p className="text-xs text-gray-400">
      {t('stats.summary', {
        chains: data.chains_count,
        stores: fmt(data.stores_count),
        prices: fmt(data.prices_count),
      })}
    </p>
  );
}
