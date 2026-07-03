// Verifies extension-owned version fields stay in sync across release files.

import { readFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const EXT_ROOT = resolve(__dirname, '..');
const REPO_ROOT = resolve(EXT_ROOT, '..');

async function readJson(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}

const sources = {
  'package.json': (await readJson(resolve(EXT_ROOT, 'package.json'))).version,
  'manifests/base.json': (await readJson(resolve(EXT_ROOT, 'manifests', 'base.json'))).version,
  '.release-please-manifest.json': (await readJson(resolve(REPO_ROOT, '.release-please-manifest.json')))['browser-extension'],
};

const versions = Object.values(sources);
const unique = [...new Set(versions)];

if (unique.length !== 1) {
  console.error('check:version failed: extension version mismatch');
  for (const [file, version] of Object.entries(sources)) {
    console.error(`  ${file}: ${version}`);
  }
  process.exit(1);
}

console.log(`check:version OK (${unique[0]})`);
