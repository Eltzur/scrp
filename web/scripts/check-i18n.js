#!/usr/bin/env node
import { readFileSync } from 'fs';
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

if (failed) process.exit(1);
console.log(`i18n key parity OK (${enKeys.size} keys in both locales)`);
