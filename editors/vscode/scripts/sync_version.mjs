#!/usr/bin/env node
// Keeps package.json's version in sync with src/gh_formatter/__init__.py's
// __version__ -- the PyPI package version is the single source of truth,
// since useBundled vendors gh-formatter straight from this repo's source.
// Run automatically before every package/publish (see vscode:prepublish).
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const initPyPath = path.join(here, '..', '..', '..', 'src', 'gh_formatter', '__init__.py');
const packageJsonPath = path.join(here, '..', 'package.json');

const initPy = readFileSync(initPyPath, 'utf8');
const match = initPy.match(/__version__\s*=\s*"([^"]+)"/);
if (!match) {
  console.error(`Could not find __version__ in ${initPyPath}`);
  process.exit(1);
}
const version = match[1];

const packageJson = JSON.parse(readFileSync(packageJsonPath, 'utf8'));
if (packageJson.version === version) {
  console.log(`package.json version already ${version}, nothing to do.`);
  process.exit(0);
}

packageJson.version = version;
writeFileSync(packageJsonPath, JSON.stringify(packageJson, null, 2) + '\n');
console.log(`package.json version set to ${version} (from __init__.py).`);
