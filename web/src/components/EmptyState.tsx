import { Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Props {
  query?: string;
}

export default function EmptyState({ query }: Props) {
  const { t } = useTranslation();
  const hasQuery = query && query.trim().length >= 2;
  const suggestions = t('suggestions', { returnObjects: true }) as string[];

  return (
    <div className="flex flex-col items-center py-20 text-center">
      <Search size={40} className="text-gray-500 mb-4" />
      {hasQuery ? (
        <>
          <p className="text-gray-600 font-medium">{t('empty.no_results', { query })}</p>
          <p className="text-gray-500 text-sm mt-1">{t('empty.no_results_hint')}</p>
        </>
      ) : (
        <>
          <p className="text-gray-600 font-medium">{t('empty.title')}</p>
          <p className="text-gray-500 text-sm mt-1">{t('empty.try')}</p>
          <div className="flex flex-wrap gap-2 justify-center mt-3">
            {suggestions.map(s => (
              <span
                key={s}
                className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600 font-medium"
              >
                {s}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
