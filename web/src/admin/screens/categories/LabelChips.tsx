import { useTranslation } from 'react-i18next';
import type { LabelBrief } from '../../api';
import { K } from './shared';

const CONF_TONE: Record<string, string> = {
  high: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  medium: 'bg-amber-50 text-amber-900 border-amber-200',
  low: 'bg-rose-50 text-rose-800 border-rose-200',
};

export default function LabelChips({ label }: { label: LabelBrief | null }) {
  const { t } = useTranslation();
  if (!label) return <span className="text-xs text-gray-500">{t(`${K}.unlabeled`)}</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-1">
      <span className={`text-xs font-semibold rounded-full border px-2 py-0.5 ${CONF_TONE[label.confidence] ?? ''}`}>
        {t(`${K}.confidence.${label.confidence}`)}
      </span>
      <span className="text-xs rounded-full border border-gray-300 bg-gray-50 text-gray-800 px-2 py-0.5">
        {t(`${K}.source.${label.source}`)}
      </span>
      {label.reviewed && (
        <span className="text-xs rounded-full border border-emerald-300 text-emerald-800 px-2 py-0.5">
          {t(`${K}.reviewed`)}
        </span>
      )}
    </span>
  );
}
