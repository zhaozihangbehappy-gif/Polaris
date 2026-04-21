const { execFileSync } = require("node:child_process");
const path = require("node:path");

const projectRoot = path.join(__dirname, "..");
const probe = [
  "const fs = require('node:fs');",
  "const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));",
  "if (pkg.name !== 'nested-demo') process.exit(2);"
].join(" ");

execFileSync(process.execPath, ["-e", probe], {
  cwd: projectRoot,
  stdio: "inherit"
});
