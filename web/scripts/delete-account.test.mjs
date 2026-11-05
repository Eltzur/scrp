// SU11A-65 (SU11A-63 L1, web): account deletion when DELETE /account succeeds
// on the server but its answer is lost. Run: npm run test:unit
import { test, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import { runAccountDeletion, unansweredDelete } from '../src/utils/deleteAccountFlow.ts';

const TIMEOUT = { kind: 'error', reason: 'timeout' };
const OFFLINE = { kind: 'error', reason: 'network' };
const HTTP500 = { kind: 'error', reason: 'http', status: 500 };
const WRONG = { ok: false, reason: 'invalid_credentials' };

/** Scripted fakes: answers are used in order; calls are recorded. */
function fakes({ auth = [], del = [] }) {
  const calls = { auth: 0, del: [] };
  return {
    calls,
    reauthenticate: async () => auth[calls.auth++] ?? WRONG,
    deleteAccount: async token => { calls.del.push(token); return del[calls.del.length - 1] ?? OFFLINE; },
  };
}
const run = (f, userId = 'u1') => runAccountDeletion({ userId, password: 'pw', ...f });

beforeEach(() => unansweredDelete.set(null));

test('normal deletion: one sign-in, one DELETE', async () => {
  const f = fakes({ auth: [{ ok: true, accessToken: 't1' }], del: [{ kind: 'deleted' }] });
  assert.deepEqual(await run(f), { kind: 'deleted', afterLostAnswer: false });
  assert.deepEqual(f.calls.del, ['t1']);
  assert.equal(unansweredDelete.get(), null);
});

test('timeout after sending: retried once with the SAME token; account_deleted = deleted', async () => {
  const f = fakes({ auth: [{ ok: true, accessToken: 't1' }], del: [TIMEOUT, { kind: 'deleted' }] });
  assert.deepEqual(await run(f), { kind: 'deleted', afterLostAnswer: true });
  assert.deepEqual(f.calls.del, ['t1', 't1']);
  assert.equal(f.calls.auth, 1);
  assert.equal(unansweredDelete.get(), null);
});

test('both lost: offline message, the attempt is remembered', async () => {
  const f = fakes({ auth: [{ ok: true, accessToken: 't1' }], del: [TIMEOUT, OFFLINE] });
  assert.deepEqual(await run(f), { kind: 'error', message: 'offline' });
  assert.deepEqual(unansweredDelete.get(), { userId: 'u1', token: 't1' });
});

test('later try: sign-in fails (login gone), the server confirms with the remembered token', async () => {
  unansweredDelete.set({ userId: 'u1', token: 't1' });
  const f = fakes({ auth: [WRONG], del: [{ kind: 'deleted' }] });   // 401 account_deleted
  assert.deepEqual(await run(f), { kind: 'deleted', afterLostAnswer: true });
  assert.deepEqual(f.calls.del, ['t1']);
  assert.equal(unansweredDelete.get(), null);
});

test('later try: pending (202) from the server also counts', async () => {
  unansweredDelete.set({ userId: 'u1', token: 't1' });
  assert.deepEqual(await run(fakes({ auth: [WRONG], del: [{ kind: 'pending' }] })), { kind: 'pending' });
});

test('later try: the check is offline or 5xx -> never "deleted"', async () => {
  unansweredDelete.set({ userId: 'u1', token: 't1' });
  assert.deepEqual(await run(fakes({ auth: [WRONG], del: [OFFLINE] })), { kind: 'error', message: 'offline' });
  assert.deepEqual(await run(fakes({ auth: [WRONG], del: [TIMEOUT] })), { kind: 'error', message: 'offline' });
  assert.deepEqual(await run(fakes({ auth: [WRONG], del: [HTTP500] })), { kind: 'error', message: 'failed' });
  assert.deepEqual(unansweredDelete.get(), { userId: 'u1', token: 't1' });   // still on record
});

test('wrong password while the account still exists -> wrong password, never "deleted"', async () => {
  unansweredDelete.set({ userId: 'u1', token: 't1' });
  const f = fakes({ auth: [WRONG], del: [{ kind: 'reauth' }] });   // token too old: the user still exists
  assert.deepEqual(await run(f), { kind: 'error', message: 'wrongPassword' });
  assert.equal(unansweredDelete.get(), null);
  // no remembered attempt: a wrong password never calls the server at all
  const g = fakes({ auth: [WRONG] });
  assert.deepEqual(await run(g), { kind: 'error', message: 'wrongPassword' });
  assert.deepEqual(g.calls.del, []);
});

test('protected account on the check -> wrong-password message, record cleared', async () => {
  unansweredDelete.set({ userId: 'u1', token: 't1' });
  assert.deepEqual(await run(fakes({ auth: [WRONG], del: [{ kind: 'protected' }] })),
    { kind: 'error', message: 'wrongPassword' });
  assert.equal(unansweredDelete.get(), null);
});

test('another user\'s remembered attempt is ignored; a sign-in network failure never checks', async () => {
  unansweredDelete.set({ userId: 'other', token: 't9' });
  const f = fakes({ auth: [WRONG] });
  assert.deepEqual(await run(f), { kind: 'error', message: 'wrongPassword' });
  assert.deepEqual(f.calls.del, []);
  unansweredDelete.set({ userId: 'u1', token: 't1' });
  const g = fakes({ auth: [{ ok: false, reason: 'network' }] });
  assert.deepEqual(await run(g), { kind: 'error', message: 'offline' });
  assert.deepEqual(g.calls.del, []);
});

test('reauth_required on the first DELETE: one more sign-in round, then deleted', async () => {
  const f = fakes({ auth: [{ ok: true, accessToken: 't1' }, { ok: true, accessToken: 't2' }],
    del: [{ kind: 'reauth' }, { kind: 'deleted' }] });
  assert.deepEqual(await run(f), { kind: 'deleted', afterLostAnswer: false });
  assert.deepEqual(f.calls.del, ['t1', 't2']);
});

test('protected and plain http errors on the first DELETE', async () => {
  assert.deepEqual(await run(fakes({ auth: [{ ok: true, accessToken: 't1' }], del: [{ kind: 'protected' }] })),
    { kind: 'error', message: 'protectedAccount' });
  assert.deepEqual(await run(fakes({ auth: [{ ok: true, accessToken: 't1' }], del: [HTTP500] })),
    { kind: 'error', message: 'failed' });
  assert.equal(unansweredDelete.get(), null);
});
