const { spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const cache = path.join(root, 'locked-npm-cache');

fs.rmSync(cache, { recursive: true, force: true });
fs.mkdirSync(cache, { recursive: true });
fs.chmodSync(cache, 0o555);

const npm = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const result = spawnSync(npm, ['--cache', cache, 'cache', 'verify'], {
  cwd: root,
  stdio: 'inherit',
  env: {
    ...process.env,
    npm_config_loglevel: 'error'
  }
});

process.exit(result.status ?? 1);
