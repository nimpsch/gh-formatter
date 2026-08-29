#!/usr/bin/env node
// Bundles src/extension.ts + its node_modules dependencies (vscode-languageclient
// and friends) into a single out/extension.js. This is what actually ships in
// the packaged VSIX -- no node_modules directory needed at runtime, which
// forecloses an entire class of "forgot to include a runtime dependency in
// .vscodeignore" bugs (one of those shipped and went undetected for a while).
import * as esbuild from 'esbuild';

const watch = process.argv.includes('--watch');

// Matches VSCode's documented esbuild problem-matcher convention (the
// [watch] lines tasks.json's background pattern looks for).
const watchLogPlugin = {
  name: 'watch-log',
  setup(build) {
    build.onStart(() => console.log('[watch] build started'));
    build.onEnd(() => console.log('[watch] build finished'));
  },
};

const options = {
  entryPoints: ['src/extension.ts'],
  bundle: true,
  outfile: 'out/extension.js',
  external: ['vscode'], // provided by the real extension host, never bundled
  format: 'cjs',
  platform: 'node',
  target: 'node18',
  sourcemap: true,
  logLevel: 'info',
  plugins: watch ? [watchLogPlugin] : [],
};

if (watch) {
  const ctx = await esbuild.context(options);
  await ctx.watch();
} else {
  await esbuild.build(options);
}
