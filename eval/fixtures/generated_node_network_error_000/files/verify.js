'use strict';

const assert = require('node:assert/strict');
const { fetchPackageMeta } = require('./registry-client');

async function main() {
  const metadata = await fetchPackageMeta('example-package');
  assert.deepEqual(metadata, { name: 'example-package', version: '1.0.0' });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
