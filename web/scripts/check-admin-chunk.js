#!/usr/bin/env node
// SU11A-54: the admin console must be a lazy chunk that shop visitors never
// download. Reads a Vite build manifest and fails if any src/admin/ module is
// reachable from index.html through STATIC imports, or if AdminApp is not a
// dynamic import of the entry. Also greps the entry chunk for the admin API
// paths as a second check.
//
//   npx vite build --manifest --outDir <dir> --emptyOutDir
//   node scripts/check-admin-chunk.js <dir>
//
// (the normal `npm run build` writes no manifest, so nothing extra is deployed)
import { readFileSync } from 'fs';
import { join, resolve } from 'path';

const dist = resolve(process.argv[2] || 'dist');
const manifest = JSON.parse(readFileSync(join(dist, '.vite', 'manifest.json'), 'utf8'));
const entry = manifest['index.html'];
if (!entry?.isEntry) {
  console.error('manifest has no index.html entry');
  process.exit(1);
}

const seen = new Set();
const walk = (key) => {
  if (seen.has(key)) return;
  seen.add(key);
  for (const imp of manifest[key]?.imports ?? []) walk(imp);
};
walk('index.html');

// AdminApp shares its chunk with admin/ui, api and format, so Rollup lists it
// as a chunk key ("_AdminApp-<hash>.js", name "AdminApp") rather than by src.
const adminKey = Object.keys(manifest).find(k =>
  manifest[k].src === 'src/admin/AdminApp.tsx' || (manifest[k].name === 'AdminApp' && !manifest[k].src));
const admin = adminKey && manifest[adminKey];
const isAdmin = (k) => k === adminKey || (manifest[k]?.src ?? '').startsWith('src/admin/');
const leaked = [...seen].filter(isAdmin);
const problems = [];
if (leaked.length) problems.push(`admin modules in the static graph of index.html: ${leaked.join(', ')}`);
if (!admin?.isDynamicEntry) problems.push('the AdminApp chunk is missing or not a dynamic entry');
if (!(entry.dynamicImports ?? []).includes(adminKey)) {
  problems.push('index.html does not import the AdminApp chunk dynamically');
}
const staticFiles = [...seen].map(k => manifest[k]?.file).filter(Boolean);
for (const f of staticFiles) {
  const js = readFileSync(join(dist, f), 'utf8');
  // Admin API paths only: the MFA calls live in supabase-js, which the shop loads anyway.
  for (const needle of ['/admin/me', '/admin/status', '/admin/audit', '/admin/ratings/history']) {
    if (js.includes(needle)) problems.push(`${f} contains "${needle}"`);
  }
}

if (problems.length) {
  problems.forEach(p => console.error(`FAIL: ${p}`));
  process.exit(1);
}
console.log(`admin chunk OK: ${admin.file} (lazy); ${staticFiles.length} static files on the shop's first load carry no admin code`);
