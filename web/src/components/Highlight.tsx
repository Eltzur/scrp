/**
 * SU11A-62: the search text marked in a product name or promotion text
 * (literal, case-insensitive; every occurrence). Text shorter than 2
 * characters is no search (as on the server), so nothing is marked.
 * Used by the promos page and the admin מבצעים cards.
 */
export default function Highlight({ text, term }: { text: string; term?: string | null }) {
  const t = (term ?? '').split(/\s+/).filter(Boolean).join(' ');
  if (t.length < 2) return <>{text}</>;
  const hay = text.toLocaleLowerCase();
  const needle = t.toLocaleLowerCase();
  const parts: React.ReactNode[] = [];
  let i = 0;
  for (let j = hay.indexOf(needle); j >= 0; j = hay.indexOf(needle, i)) {
    if (j > i) parts.push(text.slice(i, j));
    parts.push(<mark key={j} className="bg-amber-100 text-gray-900 rounded-sm">{text.slice(j, j + t.length)}</mark>);
    i = j + t.length;
  }
  if (parts.length === 0) return <>{text}</>;
  parts.push(text.slice(i));
  return <>{parts}</>;
}
