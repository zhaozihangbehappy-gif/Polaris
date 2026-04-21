const assert = require('node:assert/strict');
const { readSlowStream } = require('./runner');

(async () => {
  const output = await readSlowStream();
  assert.equal(output, 'ok');
})();
