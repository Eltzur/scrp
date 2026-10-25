#!/usr/bin/env node
import { readdirSync, readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const en = JSON.parse(readFileSync(join(__dirname, '../src/i18n/locales/en.json'), 'utf8'));
const he = JSON.parse(readFileSync(join(__dirname, '../src/i18n/locales/he.json'), 'utf8'));

function getKeys(obj, prefix = '') {
  return Object.keys(obj).flatMap(key => {
    const full = prefix ? `${prefix}.${key}` : key;
    return typeof obj[key] === 'object' && !Array.isArray(obj[key])
      ? getKeys(obj[key], full)
      : [full];
  });
}

const enKeys = new Set(getKeys(en));
const heKeys = new Set(getKeys(he));

const missingInHe = [...enKeys].filter(k => !heKeys.has(k));
const missingInEn = [...heKeys].filter(k => !enKeys.has(k));

let failed = false;

if (missingInHe.length) {
  console.error('Keys in en.json but missing in he.json:');
  missingInHe.forEach(k => console.error(`  - ${k}`));
  failed = true;
}

if (missingInEn.length) {
  console.error('Keys in he.json but missing in en.json:');
  missingInEn.forEach(k => console.error(`  - ${k}`));
  failed = true;
}

// SU11A-57: lazy string bundles (<dir>/<name>.he.json / <name>.en.json) ship
// with their own chunk; they must have the same keys too.
let lazyKeys = 0;
for (const dir of ['src/admin/i18n', 'src/components/category']) {
const lazyDir = join(__dirname, '..', dir);
for (const f of readdirSync(lazyDir).filter(f => f.endsWith('.he.json'))) {
  const base = `${dir}/${f.slice(0, -'.he.json'.length)}`;
  const name = f.slice(0, -'.he.json'.length);
  const lh = new Set(getKeys(JSON.parse(readFileSync(join(lazyDir, f), 'utf8'))));
  const le = new Set(getKeys(JSON.parse(readFileSync(join(lazyDir, `${name}.en.json`), 'utf8'))));
  for (const k of lh) if (!le.has(k)) { console.error(`${base}: missing in en: ${k}`); failed = true; }
  for (const k of le) if (!lh.has(k)) { console.error(`${base}: missing in he: ${k}`); failed = true; }
  lazyKeys += lh.size;
}
}

if (failed) process.exit(1);
console.log(`i18n key parity OK (${enKeys.size} keys in both locales; ${lazyKeys} in lazy bundles)`);
