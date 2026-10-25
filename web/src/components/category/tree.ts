import type { CategoryNode } from '../../api/client';

/** Category tree helpers for the picker and the dialogs (SU11A-57). */
export interface Row { node: CategoryNode; path: string; name: string }

export function orderedRows(nodes: CategoryNode[], lang: string): Row[] {
  const byParent = new Map<string | null, CategoryNode[]>();
  const ids = new Set(nodes.map(n => n.id));
  for (const n of nodes) {
    const p = n.parent_id && ids.has(n.parent_id) ? n.parent_id : null;
    byParent.set(p, [...(byParent.get(p) ?? []), n]);
  }
  const name = (n: CategoryNode) => (lang.startsWith('en') && n.name_en ? n.name_en : n.name_he);
  const out: Row[] = [];
  const walk = (parent: string | null, prefix: string) => {
    for (const n of byParent.get(parent) ?? []) {
      const path = prefix ? `${prefix} › ${name(n)}` : name(n);
      out.push({ node: n, path, name: name(n) });
      walk(n.id, path);
    }
  };
  walk(null, '');
  return out;
}

export function pathOf(nodes: CategoryNode[], id: string | null | undefined, lang: string): string {
  return orderedRows(nodes, lang).find(r => r.node.id === id)?.path ?? '';
}
