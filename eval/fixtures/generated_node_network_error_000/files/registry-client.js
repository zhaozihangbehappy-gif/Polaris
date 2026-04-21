'use strict';

const { requestPackage } = require('./flaky-registry');

async function fetchPackageMeta(name) {
  return requestPackage(name);
}

module.exports = { fetchPackageMeta };
