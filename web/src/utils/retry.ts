/**
 * SU11A-80 (SU11A-79 L4): load once, retry quietly on failure.
 *
 * Calls `fn`; on success hands the value to `onValue`. On failure it waits
 * delays[i] ms and tries again, at most delays.length more times, then gives up
 * silently (the caller keeps its empty state). Returns a cleanup function that
 * cancels a pending retry and drops a late answer - use it as a useEffect
 * cleanup.
 */
export const DEFAULT_RETRY_DELAYS_MS = [3000, 10000, 30000];

export function loadWithRetry<T>(
  fn: () => Promise<T>,
  onValue: (value: T) => void,
  delays: readonly number[] = DEFAULT_RETRY_DELAYS_MS,
  schedule: (cb: () => void, ms: number) => unknown = (cb, ms) => setTimeout(cb, ms),
  cancel: (handle: unknown) => void = (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
): () => void {
  let alive = true;
  let handle: unknown = null;

  const attempt = (i: number): void => {
    fn().then(
      (value) => { if (alive) onValue(value); },
      () => {
        if (!alive || i >= delays.length) return;
        handle = schedule(() => { handle = null; attempt(i + 1); }, delays[i]);
      },
    );
  };
  attempt(0);

  return () => {
    alive = false;
    if (handle !== null) cancel(handle);
  };
}
