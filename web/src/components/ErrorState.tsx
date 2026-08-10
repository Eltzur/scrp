import { AlertCircle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Props {
  onRetry?: () => void;
}

export default function ErrorState({ onRetry }: Props) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center py-20 text-center">
      <AlertCircle size={40} className="text-rose-400 mb-4" />
      <p className="text-gray-700 font-medium">{t('errors.api_down')}</p>
      <p className="text-gray-500 text-sm mt-1">
        <code className="bg-gray-100 px-1 rounded text-xs">{t('errors.api_down_hint')}</code>
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-4 flex items-center gap-2 px-4 py-2 bg-emerald-700 text-white
                     rounded-lg text-sm font-medium hover:bg-emerald-800 transition-colors"
        >
          <RefreshCw size={14} />
          {t('errors.retry')}
        </button>
      )}
    </div>
  );
}
