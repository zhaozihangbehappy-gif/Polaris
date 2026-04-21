import assert from "node:assert/strict";

const rows = [];

for (let i = 0; i < 750_000; i += 1) {
  rows.push({
    id: i,
    label: `row-${i.toString(36).padStart(6, "0")}`,
    active: (i & 1) === 0
  });
}

assert.equal(rows.length, 750_000);
