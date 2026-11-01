/**
 * Admin console location (SU11A-54, sub-views SU11A-59): the URL hash holds
 * "#tab" or "#tab/view", e.g. #categories/suggestions. A plain <a href> to one
 * of these fires hashchange, which AdminApp follows; a screen with sub-views
 * reads its first view from the hash when it mounts.
 */
export function hashParts(): [string, string | undefined] {
  const [tab, view] = window.location.hash.replace(/^#/, '').split('/', 2);
  return [tab, view];
}

/** The hash's view when it is one of `views`, else `fallback`. */
export function viewFromHash<V extends string>(views: readonly V[], fallback: V): V {
  const view = hashParts()[1];
  return view !== undefined && (views as readonly string[]).includes(view) ? (view as V) : fallback;
}

export const tabHref = (tab: string, view?: string) => `#${tab}${view ? `/${view}` : ''}`;
