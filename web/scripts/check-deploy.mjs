#!/usr/bin/env node
// SU11A-58: deploy guards for scripts/deploy_frontend.ps1.
//
//   node web/scripts/check-deploy.mjs hosts web/dist
//     Before the upload: the built JS must contain the production API host and
//     the Supabase project host (web/deploy-hosts.json, public values). A build
//     made without the production env file has neither (the API falls back to
//     localhost and the Supabase client gets an empty URL, which throws on
//     load), so it must never go live. Exit 1 = do not upload.
//
//   node web/scripts/check-deploy.mjs live web/dist [url]
//     After the upload: the index-*.js named by the local dist/index.html must
//     be the one the live site serves. Prints MATCH or MISMATCH (exit 1).
//
// Unit tests: web/scripts/check-deploy.test.mjs (fake dist, fake HTML).
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const INDEX_JS = /\/assets\/(index-[A-Za-z0-9_-]+\.js)/;

export function expectedHosts(file = join(HERE, '..', 'deploy-hosts.json')) {
  const cfg = JSON.parse(readFileSync(file, 'utf8'));
  return { api: cfg.api_host, supabase: cfg.supabase_host, live: cfg.live_url };
}

function jsFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...jsFiles(p));
    else if (name.endsWith('.js')) out.push(p);
  }
  return out;
}

/** Problems with a built dist (empty list = OK to upload). */
export function checkHosts(dist, hosts) {
  const problems = [];
  if (!hosts.api || !hosts.supabase) return ['web/deploy-hosts.json is missing api_host or supabase_host'];
  if (!existsSync(join(dist, 'index.html'))) return [`${dist}/index.html not found: did the build run?`];
  const files = existsSync(join(dist, 'assets')) ? jsFiles(join(dist, 'assets')) : [];
  if (!files.length) return [`no JS under ${dist}/assets`];
  const js = files.map(f => readFileSync(f, 'utf8')).join('\n');
  if (!js.includes(`https://${hosts.api}`)) problems.push(`the build does not contain the API host https://${hosts.api}`);
  if (!js.includes(`https://${hosts.supabase}`)) problems.push(`the build does not contain the Supabase host https://${hosts.supabase}`);
  const mainJs = indexScript(readFileSync(join(dist, 'index.html'), 'utf8'));
  if (!mainJs) problems.push('index.html names no /assets/index-*.js');
  // SU11A-81: nginx serves index.super.html on super.xxl.co.il (deploy/nginx/
  // xxl-spa-super.conf); without it every super route would be a 404.
  const superHtml = join(dist, 'index.super.html');
  if (!existsSync(superHtml)) problems.push('index.super.html not found (SU11A-81 per-host HTML): super.xxl.co.il would answer 404');
  else if (mainJs && indexScript(readFileSync(superHtml, 'utf8')) !== mainJs) problems.push('index.super.html loads a different index-*.js than index.html');
  return problems;
}

/** The index-<hash>.js an index.html loads, or null. */
export function indexScript(html) {
  const m = INDEX_JS.exec(html || '');
  return m ? m[1] : null;
}

export function compareLive(localHtml, liveHtml) {
  const local = indexScript(localHtml);
  const live = indexScript(liveHtml);
  return { local, live, match: Boolean(local) && local === live };
}

async function main(argv) {
  const [cmd, distArg, urlArg] = argv;
  const dist = resolve(distArg || 'web/dist');
  const hosts = expectedHosts();
  if (cmd === 'hosts') {
    const problems = checkHosts(dist, hosts);
    if (problems.length) {
      problems.forEach(p => console.error(`FAIL: ${p}`));
      console.error('This build was probably made without web/.env.production (or with wrong values). NOT uploading.');
      return 1;
    }
    console.log(`build OK: contains https://${hosts.api} and https://${hosts.supabase}`);
    return 0;
  }
  if (cmd === 'live') {
    const url = urlArg || hosts.live;
    let liveHtml = '';
    try {
      const res = await fetch(`${url}?deploycheck=${Date.now()}`, { headers: { 'Cache-Control': 'no-cache' } });
      liveHtml = res.ok ? await res.text() : '';
      if (!res.ok) console.error(`${url} answered HTTP ${res.status}`);
    } catch (e) {
      console.error(`could not fetch ${url}: ${e.message}`);
    }
    const r = compareLive(readFileSync(join(dist, 'index.html'), 'utf8'), liveHtml);
    console.log(`local ${r.local ?? '(none)'} | live ${r.live ?? '(none)'}`);
    console.log(r.match ? 'MATCH' : 'MISMATCH');
    return r.match ? 0 : 1;
  }
  console.error('usage: check-deploy.mjs hosts <dist> | live <dist> [url]');
  return 2;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  process.exitCode = await main(process.argv.slice(2));
}
