/**
 * SU11A-65 (SU11A-63 GAP-L1, web): the account-deletion steps, without React,
 * so the timeout paths are unit-tested (scripts/delete-account.test.mjs).
 * Same approach as the app (SU11B-5), with one difference: the "already
 * deleted" check counts only when the SERVER confirms it.
 *
 * The server commits the deletion before its Supabase call, so a DELETE
 * /account can succeed while the browser gives up (15 s timeout) or loses the
 * connection. Then:
 *   1. the same fresh token is sent once more at once; a finished deletion
 *      answers 401 account_deleted = deleted (mapDeleteAccountResponse);
 *   2. the attempt is remembered in memory (module scope: it survives leaving
 *      and re-opening the page, never stored, never logged);
 *   3. on a later try, a sign-in that fails with invalid credentials (the login
 *      is gone once Supabase deleted the user) asks the server with the
 *      remembered token. Only 'deleted' / 'pending' from the server count as
 *      deleted; offline is the offline message, a 5xx the "try again" message,
 *      and an answer proving the account still exists (reauth_required,
 *      protected) is the wrong-password message. A sign-in that fails for any
 *      other reason never reaches the check.
 */
import type { DeleteAccountResult } from '../api/client';

export type ReauthLike =
  | { ok: true; accessToken: string }
  | { ok: false; reason: 'invalid_credentials' | 'network' | 'other' };

export type DeletionOutcome =
  | { kind: 'deleted'; afterLostAnswer: boolean }
  | { kind: 'pending' }
  | { kind: 'error'; message: 'wrongPassword' | 'offline' | 'generic' | 'protectedAccount' | 'failed' };

export interface UnansweredDelete { userId: string; token: string }

let unanswered: UnansweredDelete | null = null;

/** Memory of an unanswered DELETE; exported for the tests. */
export const unansweredDelete = {
  get: (): UnansweredDelete | null => unanswered,
  set: (v: UnansweredDelete | null) => { unanswered = v; },
};

const sentButLost = (r: DeleteAccountResult) => r.kind === 'error' && r.reason !== 'http';

export async function runAccountDeletion(deps: {
  userId: string;
  password: string;
  reauthenticate: (password: string) => Promise<ReauthLike>;
  deleteAccount: (accessToken: string) => Promise<DeleteAccountResult>;
}): Promise<DeletionOutcome> {
  const { userId, password, reauthenticate, deleteAccount } = deps;
  let result: DeleteAccountResult = { kind: 'reauth' };
  let lost = false;
  // At most two rounds: the first, and one retry if the server still finds
  // the fresh token too old (clock skew, a very slow network).
  for (let round = 0; round < 2 && result.kind === 'reauth'; round++) {
    const auth = await reauthenticate(password);
    if ('reason' in auth) {
      const earlier = unanswered?.userId === userId ? unanswered : null;
      if (earlier && auth.reason === 'invalid_credentials') {
        const check = await deleteAccount(earlier.token);
        if (check.kind === 'deleted' || check.kind === 'pending') {
          unanswered = null;
          return check.kind === 'pending' ? { kind: 'pending' } : { kind: 'deleted', afterLostAnswer: true };
        }
        if (sentButLost(check)) return { kind: 'error', message: 'offline' };
        // 5xx / unexpected: cannot tell either way, so neither "deleted" nor
        // "wrong password"; the attempt stays on record.
        if (check.kind === 'error') return { kind: 'error', message: 'failed' };
        // reauth_required / protected: the account still exists, so the
        // earlier attempt deleted nothing and the password really is wrong.
        unanswered = null;
      }
      return {
        kind: 'error',
        message: auth.reason === 'invalid_credentials' ? 'wrongPassword'
          : auth.reason === 'network' ? 'offline' : 'generic',
      };
    }
    result = await deleteAccount(auth.accessToken);
    if (sentButLost(result)) {
      // Sent, answer lost: once more with the same token (still well under
      // the server's 300 s token age).
      unanswered = { userId, token: auth.accessToken };
      lost = true;
      result = await deleteAccount(auth.accessToken);
    }
  }

  if (result.kind === 'deleted' || result.kind === 'pending') {
    unanswered = null;
    return result.kind === 'pending' ? { kind: 'pending' } : { kind: 'deleted', afterLostAnswer: lost };
  }
  if (result.kind === 'protected') {
    // Protected proves nothing was deleted.
    unanswered = null;
    return { kind: 'error', message: 'protectedAccount' };
  }
  // Any other failure keeps an unanswered attempt on record for the next try.
  if (sentButLost(result)) return { kind: 'error', message: 'offline' };
  return { kind: 'error', message: 'failed' };
}
