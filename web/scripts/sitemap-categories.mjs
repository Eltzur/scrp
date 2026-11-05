#!/usr/bin/env node
// SU11A-68: the category URLs of sitemap-super.xml.
//
//   node web/scripts/sitemap-categories.mjs <browse-tree URL or JSON file> <sitemap in> <sitemap out>
//
// Rewrites the block between <!-- categories:start --> and <!-- categories:end -->
// with /categories, every department and every LINKED category / sub-category
// of GET /categories/browse-tree (linked = >= 5 visible live items in the
// current build; tobacco is never in the tree). scripts/deploy_frontend.ps1
// runs it on the built web/dist/sitemap-super.xml with the production API, so
// the sitemap follows the live tree at every deploy without a commit. When the
// API cannot be read, the committed file stays as it is (/categories and the
// 16 departments) and the script exits 2 (the deploy prints a warning and goes on).
//
// Unit tests: web/scripts/categories-seo.test.mjs.
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

export const ORIGIN = 'https://super.xxl.co.il';
const START = '<!-- categories:start -->';
const END = '<!-- categories:end -->';
const ID = /^D\d{2}(\.C\d{2}(\.S\d{2})?)?$/;

/** The category paths of a browse tree, departments first then depth-first. */
export function categoryPaths(tree) {
  const out = ['/categories'];
  const walk = (n) => {
    if (!ID.test(n.id) || n.id.startsWith('D10.C05')) return;
    if (n.level > 1 && !n.linked) return;
    out.push(`/categories/${n.id}`);
    (n.children ?? []).forEach(walk);
  };
  for (const d of tree.departments ?? []) {
    if ((d.count ?? 0) > 0) walk(d);
  }
  return [...new Set(out)];
}

/** The sitemap with its category block replaced. Throws when the markers are missing. */
export function renderSitemap(xml, paths, lastmod) {
  const a = xml.indexOf(START);
  const b = xml.indexOf(END);
  if (a < 0 || b < a) throw new Error('sitemap: category markers not found');
  const lines = paths.map(p => `  <url><loc>${ORIGIN}${p}</loc><lastmod>${lastmod}</lastmod></url>`);
  return xml.slice(0, a + START.length) + '\n' + lines.join('\n') + '\n  ' + xml.slice(b);
}

async function readTree(src) {
  if (/^https?:\/\//.test(src)) {
    const res = await fetch(src, { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(20000) });
    if (!res.ok) throw new Error(`${src}: HTTP ${res.status}`);
    return res.json();
  }
  return JSON.parse(readFileSync(src, 'utf8'));
}

async function main([src, input, output]) {
  if (!src || !input || !output) {
    console.error('usage: sitemap-categories.mjs <browse-tree URL|file> <sitemap in> <sitemap out>');
    process.exit(1);
  }
  let tree;
  try {
    tree = await readTree(src);
  } catch (e) {
    console.error(`WARN: browse tree not read (${e.message}); the sitemap keeps its committed category block`);
    process.exit(2);
  }
  const paths = categoryPaths(tree);
  const lastmod = (tree.built_at ?? new Date().toISOString()).slice(0, 10);
  writeFileSync(output, renderSitemap(readFileSync(input, 'utf8'), paths, lastmod));
  console.log(`sitemap: ${paths.length} category URLs (${output})`);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main(process.argv.slice(2));
}
