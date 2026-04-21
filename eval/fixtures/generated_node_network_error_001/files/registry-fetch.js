const { setTimeout: sleep } = require('node:timers/promises');

const npmConfig = {
  fetchTimeout: 30,
  fetchRetries: 0
};

async function simulatedRegistryFetch(attempt) {
  const responseDelay = attempt === 0 ? 200 : 80;
  await sleep(responseDelay);
  return { statusCode: 200, body: JSON.stringify({ name: 'tiny-package', version: '1.0.0' }) };
}

async function fetchOnce(attempt, timeoutMs) {
  const timeout = sleep(timeoutMs).then(() => {
    const err = new Error(`connect ETIMEDOUT registry.npmjs.org after ${timeoutMs}ms`);
    err.code = 'ETIMEDOUT';
    throw err;
  });

  return Promise.race([simulatedRegistryFetch(attempt), timeout]);
}

async function fetchWithRetry() {
  let lastError;

  for (let attempt = 0; attempt <= npmConfig.fetchRetries; attempt += 1) {
    try {
      return await fetchOnce(attempt, npmConfig.fetchTimeout);
    } catch (err) {
      lastError = err;
      if (err.code !== 'ETIMEDOUT') {
        throw err;
      }
    }
  }

  throw lastError;
}

async function main() {
  const response = await fetchWithRetry();
  const pkg = JSON.parse(response.body);
  if (response.statusCode !== 200 || pkg.name !== 'tiny-package') {
    throw new Error('Unexpected registry response');
  }
}

if (require.main === module) {
  main();
}

module.exports = { fetchWithRetry };
