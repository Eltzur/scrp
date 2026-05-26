import { useState } from 'react';
import { useFreshness } from '../api/hooks';

function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()}.${d.getUTCMonth() + 1}.${d.getUTCFullYear()}`;
}

function relativeHe(iso: string | null): string {
  if (!iso) return 'לא עודכן';
  const then = new Date(iso);
  const now  = new Date();
  // Truncate both to UTC calendar date so same-date runs always produce the same count
  const thenDay = Date.UTC(then.getUTCFullYear(), then.getUTCMonth(), then.getUTCDate());
  const nowDay  = Date.UTC(now.getUTCFullYear(),  now.getUTCMonth(),  now.getUTCDate());
  const diffDays = (nowDay - thenDay) / 86_400_000;
  if (diffDays <= 0) return 'היום';
  if (diffDays === 1) return 'אתמול';
  if (diffDays === 2) return 'לפני יומיים';
  return `לפני ${diffDays} ימים`;
}

export default function FreshnessStrip() {
  const { data } = useFreshness();
  const [expanded, setExpanded] = useState(false);

  if (!data) return null;

  return (
    <div className="text-xs text-gray-400">
      <button
        onClick={() => setExpanded(e => !e)}
        className="flex items-center gap-1 hover:text-gray-500 transition-colors"
      >
        <span>סטטוס עדכון מחירים</span>
        <span aria-hidden>{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <ul className="mt-1 space-y-0.5">
          {data.chains.map(c => (
            <li key={c.chain_name}>
              {c.chain_name} — עודכן{' '}
              {c.last_loaded_at
                ? `${relativeHe(c.last_loaded_at)} (${formatDate(c.last_loaded_at)})`
                : 'לא עודכן'}
            </li>
          ))}
        </ul>
        <p className="mt-1 text-gray-300">* עדכון מחירים מתבצע בשעות הצהריים</p>
      )}
    </div>
  );
}
