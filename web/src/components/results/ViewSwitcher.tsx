import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { LayoutGrid, List, Table2 } from 'lucide-react';
import clsx from 'clsx';
import { K } from './strings';
import {
  LIST_PAGE_SIZES, TABLE_PAGE_SIZES, VIEW_MODES, effectivePageSize,
  type PageSize, type ViewMode,
} from '../../utils/resultViews';

const ICON = { grid: LayoutGrid, list: List, table: Table2 } as const;

interface Props {
  view: ViewMode;
  /** The remembered choice; differs from `view` when list / table are not available here. */
  wanted?: ViewMode;
  size: PageSize;
  onView: (v: ViewMode) => void;
  onSize: (n: PageSize) => void;
  /** false: list / table are not available (group_by=store); only the grid button is enabled. */
  pagedAvailable: boolean;
}

/**
 * SU11A-72: "רשת / רשימה / טבלת השוואה" above the results, with the page size
 * next to it (list + table only). Real buttons with aria-pressed; nothing goes
 * into the URL.
 */
export default function ViewSwitcher({ view, wanted, size, onView, onSize, pagedAvailable }: Props) {
  const { t } = useTranslation();
  const sizeId = useId();
  const eff = effectivePageSize(view, size);
  const sizes = view === 'table' ? TABLE_PAGE_SIZES : LIST_PAGE_SIZES;
  return (
    <div className="flex flex-wrap items-center gap-3 mb-3">
      <div role="group" aria-label={t(`${K}.label`)} className="inline-flex rounded-lg border border-gray-500 bg-white p-0.5">
        {VIEW_MODES.map(m => {
          const Icon = ICON[m];
          const disabled = m !== 'grid' && !pagedAvailable;
          const on = m === view && !disabled;
          return (
            <button
              key={m}
              type="button"
              aria-pressed={on}
              disabled={disabled}
              onClick={() => onView(m)}
              className={clsx(
                'inline-flex items-center gap-1.5 min-h-[36px] px-3 rounded-md text-sm font-medium',
                'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700',
                on ? 'bg-emerald-700 text-white' : 'text-gray-800 hover:bg-gray-100',
                disabled && 'opacity-50 cursor-not-allowed hover:bg-transparent',
              )}
            >
              <Icon size={15} aria-hidden="true" />
              {t(`${K}.${m}`)}
            </button>
          );
        })}
      </div>
      {view !== 'grid' && pagedAvailable && (
        <label htmlFor={sizeId} className="flex items-center gap-2 text-sm text-gray-800">
          {t(`${K}.page_size`)}
          <select
            id={sizeId}
            value={eff.size}
            onChange={e => onSize(Number(e.target.value) as PageSize)}
            className="min-h-[36px] rounded-lg border border-gray-500 bg-white px-2 text-sm text-gray-900
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-700"
          >
            {sizes.map(n => <option key={n} value={n}>{n === 0 ? t(`${K}.all`) : n}</option>)}
          </select>
        </label>
      )}
      {!pagedAvailable && wanted && wanted !== 'grid' && (
        <p className="text-xs text-gray-700">{t(`${K}.store_mode`)}</p>
      )}
    </div>
  );
}
