import { useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { Search } from 'lucide-react';
import clsx from 'clsx';
import { useTranslation } from 'react-i18next';
import type { CategoryNode } from '../../api/client';
import { orderedRows, type Row } from './tree';
import './strings';

/**
 * Searchable category tree picker (SU11A-57), shared by the shop's
 * "הצעת עדכון קטגוריה" dialog and the admin console. Never in the shop's main
 * chunk: both callers import it lazily.
 *
 * WAI-ARIA combobox pattern: focus stays in the search box, ArrowUp / ArrowDown
 * move the active option (aria-activedescendant), Enter picks it. Without a
 * query the whole tree shows, indented by level; with one, every node whose
 * path contains all the words. Options are at least 44 px tall.
 */
interface Props {
  nodes: CategoryNode[];
  value: string | null;
  onChange: (id: string) => void;
  /** The item's current category: shown, marked, not selectable. */
  currentId?: string | null;
  /** Visible label of the search box. */
  label: string;
  maxHeightClass?: string;
}

export default function CategoryPicker({ nodes, value, onChange, currentId, label, maxHeightClass = 'max-h-72' }: Props) {
  const { t, i18n } = useTranslation();
  const uid = useId();
  const listId = `${uid}-list`;
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

  const all = useMemo(() => orderedRows(nodes, i18n.language), [nodes, i18n.language]);
  const rows = useMemo(() => {
    const words = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return all;
    return all.filter(r => {
      const hay = `${r.path} ${r.node.id}`.toLocaleLowerCase();
      return words.every(w => hay.includes(w));
    });
  }, [all, query]);
  const filtered = query.trim().length > 0;
  const activeIdx = Math.min(active, Math.max(rows.length - 1, 0));

  const optId = (id: string) => `${uid}-opt-${id.replace(/\./g, '-')}`;
  const move = (to: number) => {
    const next = Math.max(0, Math.min(rows.length - 1, to));
    setActive(next);
    const el = rows[next] && document.getElementById(optId(rows[next].node.id));
    el?.scrollIntoView({ block: 'nearest' });
  };
  const pick = (r: Row | undefined) => {
    if (r && r.node.id !== currentId) onChange(r.node.id);
  };
  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); move(activeIdx + 1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(activeIdx - 1); }
    else if (e.key === 'Home' && e.ctrlKey) { e.preventDefault(); move(0); }
    else if (e.key === 'End' && e.ctrlKey) { e.preventDefault(); move(rows.length - 1); }
    else if (e.key === 'Enter') { e.preventDefault(); pick(rows[activeIdx]); }
  };

  return (
    <div>
      <label htmlFor={`${uid}-q`} className="block text-sm font-semibold text-gray-800 mb-1">{label}</label>
      <div className="relative">
        <Search size={16} className="absolute top-1/2 -translate-y-1/2 start-3 text-gray-500 pointer-events-none"
          aria-hidden="true" />
        <input
          id={`${uid}-q`}
          type="search"
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={rows[activeIdx] ? optId(rows[activeIdx].node.id) : undefined}
          value={query}
          onChange={e => { setQuery(e.target.value); setActive(0); }}
          onKeyDown={onKey}
          placeholder={t('category.picker_placeholder')}
          dir="auto"
          autoComplete="off"
          className="w-full min-h-[44px] ps-9 pe-3 rounded-xl border border-gray-300 text-sm
            focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent"
        />
      </div>
      <p className="sr-only" aria-live="polite">{t('category.picker_results', { n: rows.length })}</p>
      <ul
        id={listId}
        ref={listRef}
        role="listbox"
        aria-label={label}
        className={clsx('mt-2 overflow-y-auto rounded-xl border border-gray-200 divide-y divide-gray-100', maxHeightClass)}
      >
        {rows.length === 0 && (
          <li className="p-3 text-sm text-gray-600" role="presentation">{t('category.picker_empty')}</li>
        )}
        {rows.map((r, i) => {
          const selected = r.node.id === value;
          const isCurrent = r.node.id === currentId;
          return (
            <li
              key={r.node.id}
              id={optId(r.node.id)}
              role="option"
              aria-selected={selected}
              aria-disabled={isCurrent || undefined}
              onMouseDown={e => e.preventDefault()}
              onClick={() => { setActive(i); pick(r); }}
              className={clsx(
                'min-h-[44px] px-3 py-2 flex items-center justify-between gap-2 text-sm cursor-pointer',
                i === activeIdx && 'ring-2 ring-inset ring-emerald-500',
                selected ? 'bg-emerald-50 text-emerald-900 font-semibold' : 'hover:bg-gray-50 text-gray-900',
                isCurrent && 'cursor-not-allowed text-gray-500',
                !filtered && r.node.level === 1 && 'font-bold',
              )}
              style={filtered ? undefined : { paddingInlineStart: `${0.75 + (r.node.level - 1) * 1.25}rem` }}
            >
              <span className="min-w-0 break-words" dir="auto">{filtered ? r.path : r.name}</span>
              {isCurrent && <span className="shrink-0 text-xs text-gray-500">{t('category.current_mark')}</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
