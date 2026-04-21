const fs = require("fs");

fs.writeFileSync("dist/out.txt", "polaris-ok\n");
console.log("built");
