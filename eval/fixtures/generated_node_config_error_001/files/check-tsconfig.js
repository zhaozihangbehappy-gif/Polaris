const fs = require("node:fs");

const path = "tsconfig.json";

let raw;
try {
  raw = fs.readFileSync(path, "utf8");
} catch (err) {
  process.stderr.write(`Cannot read file '${path}': ${err.message}\n`);
  process.exit(1);
}

let config;
try {
  config = JSON.parse(raw);
} catch (err) {
  process.stderr.write(`${path}: error TS5083: ${err.message}\n`);
  process.exit(1);
}

if (!config || typeof config !== "object" || Array.isArray(config)) {
  process.stderr.write(`${path}: error TS5024: Compiler option root must be an object.\n`);
  process.exit(1);
}

process.exit(0);
