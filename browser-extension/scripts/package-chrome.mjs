// Package Chrome extension into zip artifact.
// Used for store submission preparation.

import { execSync } from 'child_process';
import { writeFileSync, mkdirSync, existsSync, rmSync } from 'fs';
import { resolve } from 'path';
import { fileURLToPath } from 'url';
import process from 'process';

const __dirname = fileURLToPath(import.meta.url);
const ROOT = resolve(__dirname, '..');
const DIST = resolve(ROOT, 'dist', 'chrome');
const ARTIFACTS = resolve(ROOT, 'artifacts');

async function main() {
  const version = JSON.parse(
    readFileSync(resolve(ROOT, 'package.json'), 'utf8')
  ).version;

  // Ensure artifacts directory exists
  if (!existsSync(ARTIFACTS)) {
    mkdirSync(ARTIFACTS, { recursive: true });
  }

  const zipName = `abs-media-importer-chrome-v${version}.zip`;
  const zipPath = resolve(ARTIFACTS, zipName);

  // Remove existing artifact
  if (existsSync(zipPath)) {
    rmSync(zipPath);
  }

  // Create zip file
  console.log(`Packaging Chrome extension: ${zipName}`);
  execSync(`cd "${DIST}" && zip -r "${zipPath}" .`, { stdio: 'inherit' });

  console.log(`Chrome extension packaged: ${zipPath}`);

  // Verify package contents
  const stats = execSync(`unzip -l "${zipPath}" | head -20`, { encoding: 'utf8', cwd: ARTIFACTS });
  console.log('Package contents (first 20 lines):');
  console.log(stats);

  // List contents to exclude unwanted files
  console.log('\nChecking for unwanted files in package...');

  const unwantedPatterns = [
    '*.git',
    'node_modules/**',
    'tests/**',
    'docs/**',
    '*.map',
    'artifacts/**',
    'dist/firefox/**',
    '*.env',
    '.env*',
  ];

  const listCommand = `unzip -l "${zipPath}" | grep -E '(\\.git|node_modules|tests|docs|\\.map|artifacts|dist/firefox|\\.env)' || echo 'No unwanted files found'`;

  try {
    const unwantedOutput = execSync(listCommand, { encoding: 'utf8', cwd: ARTIFACTS });
    if (unwantedOutput.includes('node_modules') || unwantedOutput.includes('tests') || unwantedOutput.includes('docs')) {
      console.warn('\nWARNING: Package contains unwanted files:');
      console.warn(unwantedOutput);
      console.warn('\nThese files should be excluded before store submission.');
    }
  } catch (error) {
    console.log('No unwanted files found (good!)');
  }

  console.log('\nPackaging complete!');
}

function readFileSync(path) {
  const { readFileSync } from 'fs';
  return readFileSync(path, 'utf8');
}

main().catch(error => {
  console.error('Packaging failed:', error);
  process.exit(1);
});
