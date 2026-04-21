const fs = require("node:fs");

try {
  JSON.parse(fs.readFileSync("package.json", "utf8"));
} catch (error) {
  throw new Error(`package.json parse failed: ${error.message}`);
}
