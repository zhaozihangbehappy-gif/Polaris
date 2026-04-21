'use strict';

const { existsSync } = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const root = path.resolve(__dirname, '..');
const pkg = require(path.join(root, 'package.json'));

if (pkg.config && pkg.config.build_from_source === false) {
  console.log('using prebuilt native binary');
  process.exit(0);
}

const npmExecPath = process.env.npm_execpath;
if (!npmExecPath) {
  throw new Error('run this verifier through npm so npm-bundled node-gyp is available');
}

const nodeGyp = path.resolve(
  path.dirname(npmExecPath),
  '..',
  'node_modules',
  'node-gyp',
  'bin',
  'node-gyp.js'
);

if (!existsSync(nodeGyp)) {
  throw new Error(`node-gyp not found at ${nodeGyp}`);
}

const result = spawnSync(process.execPath, [nodeGyp, 'rebuild', '--nodedir=/usr'], {
  cwd: root,
  stdio: 'inherit'
});

process.exit(result.status === null ? 1 : result.status);
