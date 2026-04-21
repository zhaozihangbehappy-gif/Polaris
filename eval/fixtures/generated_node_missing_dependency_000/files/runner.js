'use strict';

const { createRequire } = require('module');

const sandboxRequire = createRequire('/tmp/polaris-node-missing-dependency/virtual-entry.js');
const greet = sandboxRequire('local-greeter');

if (greet('agent') !== 'hello, agent') {
  throw new Error('unexpected greeting');
}

console.log(greet('agent'));
