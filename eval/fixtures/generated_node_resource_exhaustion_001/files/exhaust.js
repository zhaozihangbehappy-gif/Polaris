const fs = require("node:fs");
const path = require("node:path");

const target = path.join(__dirname, "payload.txt");
const descriptors = [];

for (let i = 0; i < 256; i += 1) {
  descriptors.push(fs.openSync(target, "r"));
}

for (const fd of descriptors) {
  fs.closeSync(fd);
}

console.log(`opened ${descriptors.length} descriptors`);
