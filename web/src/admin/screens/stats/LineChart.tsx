import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { linePaths, shortDay } from './statsView';
import { COL_NUM, COL_TEXT } from '../../ui';

/**
 * A small SVG line chart (SU11A-69), no chart library: it ships only in the
 * admin chunk. Series are told apart by line pattern AND a text legend, never
 * by colour alone (IS 5568); the numbers are also in a table under
 * "הצגת הנתונים כטבלה" for screen readers and keyboard users.
 */
export interface Line { label: string; values: (number | null)[] }

const STYLES = [
  { stroke: '#047857', dash: undefined },      // emerald-700, solid
  { stroke: '#b45309', dash: '6 4' },          // amber-700, dashed
  { stroke: '#1d4ed8', dash: '2 3' },          // blue-700, dotted
  { stroke: '#7e22ce', dash: '10 3 2 3' },     // purple-700, dash-dot
  { stroke: '#374151', dash: '1 5' },          // gray-700, sparse dots
];
const W = 600;
const H = 150;

export default function LineChart({ title, days, lines }: { title: string; days: string[]; lines: Line[] }) {
  const { t } = useTranslation();
  const id = useId();
  const max = Math.max(0, ...lines.flatMap(l => l.values.filter((v): v is number => v != null)));
  const fmt = (v: number | null) => (v == null ? '—' : v.toLocaleString('he-IL'));
  const sums = lines.map(l => `${l.label}: ${fmt(l.values.reduce<number>((a, v) => a + (v ?? 0), 0))}`).join(', ');

  return (
    <figure className="mt-3">
      <figcaption id={`${id}-t`} className="text-sm font-semibold text-gray-800">{title}</figcaption>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 mt-1 text-xs text-gray-700">
        {lines.map((l, i) => (
          <li key={l.label} className="inline-flex items-center gap-1.5">
            <svg width="28" height="8" aria-hidden="true">
              <line x1="0" y1="4" x2="28" y2="4" stroke={STYLES[i % STYLES.length].stroke} strokeWidth="2.5"
                strokeDasharray={STYLES[i % STYLES.length].dash} />
            </svg>
            {l.label}
          </li>
        ))}
      </ul>
      <div dir="ltr" className="mt-1">
        <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-36" role="img" aria-labelledby={`${id}-t ${id}-d`}
          preserveAspectRatio="none">
          <desc id={`${id}-d`}>{`${shortDay(days[0] ?? '')}–${shortDay(days[days.length - 1] ?? '')}. ${sums}`}</desc>
          <line x1="0" y1={H - 4} x2={W} y2={H - 4} stroke="#d1d5db" strokeWidth="1" />
          {lines.map((l, i) => linePaths(l.values, max, W, H).map((pts, j) => (
            <polyline key={`${i}-${j}`} points={pts} fill="none" stroke={STYLES[i % STYLES.length].stroke}
              strokeWidth="2.5" strokeDasharray={STYLES[i % STYLES.length].dash} vectorEffect="non-scaling-stroke" />
          )))}
        </svg>
        <div className="flex justify-between text-xs text-gray-600 tabular-nums">
          <span>{days.length ? shortDay(days[0]) : ''}</span>
          <span>{t('admin.stats.chart_max', { n: fmt(max) })}</span>
          <span>{days.length ? shortDay(days[days.length - 1]) : ''}</span>
        </div>
      </div>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer min-h-[44px] inline-flex items-center text-emerald-800 underline underline-offset-4
          focus-visible:outline focus-visible:outline-2 focus-visible:outline-emerald-700 rounded">
          {t('admin.stats.chart_table')}
        </summary>
        <div className="overflow-x-auto max-h-64 overflow-y-auto mt-1">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-gray-600 border-b border-gray-200">
                <th scope="col" className={`py-1 px-1 font-medium ${COL_TEXT}`}>{t('admin.stats.day')}</th>
                {lines.map(l => <th key={l.label} scope="col" className={`py-1 px-1 font-medium ${COL_NUM}`}>{l.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {days.map((d, i) => (
                <tr key={d} className="border-b border-gray-100 last:border-0">
                  <th scope="row" className={`py-1 px-1 font-normal tabular-nums ${COL_TEXT}`}><span dir="ltr">{d}</span></th>
                  {lines.map(l => <td key={l.label} className={`py-1 px-1 ${COL_NUM}`}><span dir="ltr">{fmt(l.values[i])}</span></td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </figure>
  );
}
