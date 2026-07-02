// Builds unpacked extensions for Chrome and Firefox into dist/<browser>/.
// Copies src/* + icons/, then writes the per-browser manifest at the root.

import { cp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import process from 'node:process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');
const TARGETS = ['chrome', 'firefox'];

async function build(target) {
  const dist = resolve(ROOT, 'dist', target);
  await rm(dist, { recursive: true, force: true });
  await mkdir(dist, { recursive: true });

  // Copy the icons directory (referenced by manifest + notifications API).
  await cp(resolve(ROOT, 'icons'), resolve(dist, 'icons'), { recursive: true });

  // Copy source files the manifest references directly to the dist root,
  // plus the shared ES modules they import. Skip the standalone src/ folder.
  const entries = ['popup.html', 'popup.js', 'options.html', 'options.js', 'background.js'];
  for (const name of entries) {
    await cp(resolve(ROOT, 'src', name), resolve(dist, name));
  }
  // Shared modules imported by the entry points.
  await cp(resolve(ROOT, 'src', 'settings.js'), resolve(dist, 'settings.js'));
  await cp(resolve(ROOT, 'src', 'browser-api.js'), resolve(dist, 'browser-api.js'));

  // Merge the per-browser manifest with the shared base and write it to the dist root.
  const base = JSON.parse(await readFile(resolve(ROOT, 'manifests', 'base.json'), 'utf8'));
  const overrides = JSON.parse(await readFile(resolve(ROOT, 'manifests', `${target}.json`), 'utf8'));
  const manifest = { ...base, ...overrides };
  // Firefox uses background.scripts; Chrome uses background.service_worker.
  if (target === 'chrome') {
    delete manifest.background?.scripts;
  } else if (target === 'firefox') {
    delete manifest.background?.service_worker;
  }
  await writeFile(resolve(dist, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\n', 'utf8');

  console.log(`Built ${target} -> dist/${target}/`);
}

const requested = process.argv.slice(2).filter((a) => TARGETS.includes(a));
const targets = requested.length ? requested : TARGETS;
for (const t of targets) await build(t);