const fs = require("node:fs");
const path = require("node:path");

const configPath = path.join(__dirname, "data", "config.json");
const config = JSON.parse(fs.readFileSync(configPath, "utf8"));

if (config.mode !== "ready") {
  throw new Error("config.mode must be ready");
}

console.log(`mode=${config.mode}`);
