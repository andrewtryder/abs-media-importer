// Lightweight lint: validates that every entry point referenced by the manifests
// exists in src/, and that the JS parses with node --check. Exits non-zero on failure.

import { access, readFile, rm, writeFile, mkdir, cp } from 'node:fs/promises';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const run = promisify(execFile);
const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');

async function exists(p) {
  try { await access(p); return true; } catch { return false; }
}

async function checkSyntax(file) {
  try {
    await run('node', ['--check', file]);
  } catch (err) {
    throw new Error(`${file}: syntax error\n${err.stderr || err.stdout || err.message}`);
  }
}

const manifestFiles = ['chrome.json', 'firefox.json', 'base.json'];
for (const f of manifestFiles) {
  const path = resolve(ROOT, 'manifests', f);
  if (!(await exists(path))) throw new Error(`Missing manifest: ${path}`);
}

// Gather entry points from each manifest and verify the source files exist.
const entryPoints = new Set(['popup.html', 'popup.js', 'options.html', 'options.js', 'background.js']);
for (const f of ['chrome.json', 'firefox.json']) {
  const manifest = JSON.parse(await readFile(resolve(ROOT, 'manifests', f), 'utf8'));
  if (manifest.action?.default_popup) entryPoints.add(manifest.action.default_popup);
  if (manifest.options_ui?.page) entryPoints.add(manifest.options_ui.page);
  if (manifest.background?.service_worker) entryPoints.add(manifest.background.service_worker);
  for (const s of manifest.background?.scripts || []) entryPoints.add(s);
}

for (const name of entryPoints) {
  const src = resolve(ROOT, 'src', name);
  if (!(await exists(src))) throw new Error(`Missing entry point src/${name} (referenced by manifest)`);
  if (name.endsWith('.js')) await checkSyntax(src);
}

console.log('lint: OK');