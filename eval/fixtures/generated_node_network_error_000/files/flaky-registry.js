'use strict';

let attempts = 0;

async function requestPackage(name) {
  attempts += 1;

  if (attempts === 1) {
    const error = new Error('connect ECONNREFUSED 127.0.0.1:4873');
    error.code = 'ECONNREFUSED';
    error.errno = -111;
    error.syscall = 'connect';
    error.address = '127.0.0.1';
    error.port = 4873;
    throw error;
  }

  return { name, version: '1.0.0' };
}

module.exports = { requestPackage };
