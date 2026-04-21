const assert = require("node:assert/strict");

const timeoutArg = process.argv.find((arg) => arg.startsWith("--testTimeout="));
const timeoutMs = timeoutArg ? Number(timeoutArg.split("=")[1]) : 50;

function slowOperation() {
  return new Promise((resolve) => setTimeout(() => resolve("done"), 60));
}

async function runTest(name, fn) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      reject(
        new Error(
          `Exceeded timeout of ${timeoutMs} ms for a test. Use jest.setTimeout(newTimeout) or run with --testTimeout=<ms>.`
        )
      );
    }, timeoutMs);
  });

  try {
    await Promise.race([fn(), timeout]);
    clearTimeout(timer);
    console.log(`ok - ${name}`);
  } catch (error) {
    clearTimeout(timer);
    console.error(error.message);
    process.exitCode = 1;
  }
}

runTest("slow operation finishes", async () => {
  assert.equal(await slowOperation(), "done");
});
