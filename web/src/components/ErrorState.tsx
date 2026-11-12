import { AlertCircle, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface Props {
  onRetry?: () => void;
  /** The server answered 429 / 503: it is up but busy (SU11A-49). */
  busy?: boolean;
}

export default function ErrorState({ onRetry, busy }: Props) {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col items-center py-20 text-center">
      <AlertCircle size={40} className="text-rose-400 mb-4" />
      <p className="text-gray-700 font-medium" role="alert">
        {busy ? t('errors.busy') : t('errors.api_down')}
      </p>
      {/* SU11A-80 (SU11A-79 H1): customer text only - no developer hint, no code box. */}
      {!busy && (
        <p className="text-gray-600 text-sm mt-1">{t('errors.api_down_hint')}</p>
      )}
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
