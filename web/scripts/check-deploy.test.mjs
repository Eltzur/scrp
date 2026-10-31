// SU11A-58: the deploy guards (check-deploy.mjs) against fake dists. Run: npm run test:unit
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { checkHosts, compareLive, expectedHosts, indexScript } from './check-deploy.mjs';

const HOSTS = { api: 'api.example.test', supabase: 'proj.supabase.example' };
const SCRIPT = fileURLToPath(new URL('./check-deploy.mjs', import.meta.url));

function fakeDist(js, html = '<script type="module" src="/assets/index-AbC_12-x.js"></script>') {
  const dir = mkdtempSync(join(tmpdir(), 'xxl-dist-'));
  mkdirSync(join(dir, 'assets'));
  writeFileSync(join(dir, 'index.html'), html);
  writeFileSync(join(dir, 'assets', 'index-AbC_12-x.js'), js);
  return dir;
}

test('a production build passes', () => {
  const d = fakeDist('const a="https://api.example.test",b="https://proj.supabase.example";');
  try { assert.deepEqual(checkHosts(d, HOSTS), []); } finally { rmSync(d, { recursive: true }); }
});

test('a build without the env file fails on both hosts', () => {
  const d = fakeDist('const a=void 0||"http://localhost:8000";createClient("","")');
  try {
    const p = checkHosts(d, HOSTS);
    assert.equal(p.length, 2);
    assert.match(p[0], /API host/);
    assert.match(p[1], /Supabase host/);
  } finally { rmSync(d, { recursive: true }); }
});

test('one host missing, a host in a lazy chunk, no index, no assets', () => {
  const d = fakeDist('x="https://api.example.test"');
  try {
    assert.deepEqual(checkHosts(d, HOSTS), ['the build does not contain the Supabase host https://proj.supabase.example']);
    writeFileSync(join(d, 'assets', 'Admin-1.js'), 'y="https://proj.supabase.example"');
    assert.deepEqual(checkHosts(d, HOSTS), []);
    writeFileSync(join(d, 'index.html'), '<html></html>');
    assert.deepEqual(checkHosts(d, HOSTS), ['index.html names no /assets/index-*.js']);
  } finally { rmSync(d, { recursive: true }); }
  const empty = mkdtempSync(join(tmpdir(), 'xxl-dist-'));
  try {
    assert.match(checkHosts(empty, HOSTS)[0], /index.html not found/);
    writeFileSync(join(empty, 'index.html'), 'x');
    assert.match(checkHosts(empty, HOSTS)[0], /no JS/);
  } finally { rmSync(empty, { recursive: true }); }
  assert.match(checkHosts('nowhere', { api: '', supabase: 'x' })[0], /deploy-hosts.json/);
});

test('live comparison: MATCH only on the same index-*.js', () => {
  const a = '<script src="/assets/index-AAA.js"></script>';
  const b = '<script src="/assets/index-BBB.js"></script>';
  assert.equal(indexScript(a), 'index-AAA.js');
  assert.equal(indexScript(''), null);
  assert.deepEqual(compareLive(a, a), { local: 'index-AAA.js', live: 'index-AAA.js', match: true });
  assert.equal(compareLive(a, b).match, false);
  assert.equal(compareLive(a, '').match, false);                 // fetch failed
  assert.equal(compareLive('', '').match, false);                // never MATCH on two blanks
});

test('the committed config names the production hosts', () => {
  const h = expectedHosts();
  assert.equal(h.api, 'api-super.xxl.co.il');
  assert.match(h.supabase, /^[a-z0-9]+\.supabase\.co$/);
  assert.equal(h.live, 'https://super.xxl.co.il/');
});

test('CLI: exit 1 and no OK line on a bad build', () => {
  const d = fakeDist('nothing here');
  try {
    const r = spawnSync(process.execPath, [SCRIPT, 'hosts', d], { encoding: 'utf8' });
    assert.equal(r.status, 1);
    assert.match(r.stderr, /NOT uploading/);
    assert.doesNotMatch(r.stdout, /build OK/);
  } finally { rmSync(d, { recursive: true }); }
});
