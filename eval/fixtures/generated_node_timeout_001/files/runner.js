const { Readable, Writable } = require('node:stream');
const { pipeline } = require('node:stream/promises');

const DEFAULT_TIMEOUT_MS = 50;
const STREAM_DELAY_MS = 120;

function delayedReadable(delayMs) {
  let started = false;
  return new Readable({
    read() {
      if (started) {
        return;
      }

      started = true;
      setTimeout(() => {
        this.push('ok');
        this.push(null);
      }, delayMs);
    },
  });
}

async function readSlowStream(timeoutMs = DEFAULT_TIMEOUT_MS) {
  let output = '';
  const sink = new Writable({
    write(chunk, encoding, callback) {
      output += chunk.toString();
      callback();
    },
  });

  try {
    await pipeline(delayedReadable(STREAM_DELAY_MS), sink, {
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error(`operation timed out after ${timeoutMs}ms`, {
        cause: error,
      });
    }

    throw error;
  }

  return output;
}

module.exports = { readSlowStream };
