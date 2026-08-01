#!/usr/bin/env node
// Visual regression: compare two PNG screenshots, write diff.png + print metrics.
// Usage: node scripts/visual-diff.mjs <before.png> <after.png> [<diff.png>] [<threshold=0.1>]
//
// Exits 0 always — printing percentage so a wrapper can decide what's "regression".
import fs from 'node:fs';
import path from 'node:path';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';

const [, , beforePath, afterPath, diffPathArg, thresholdArg] = process.argv;
if (!beforePath || !afterPath) {
  console.error('Usage: visual-diff.mjs <before.png> <after.png> [<diff.png>] [<threshold>]');
  process.exit(2);
}
const diffPath = diffPathArg || path.join(path.dirname(afterPath), 'diff.png');
const threshold = thresholdArg ? parseFloat(thresholdArg) : 0.1;

const before = PNG.sync.read(fs.readFileSync(beforePath));
const after  = PNG.sync.read(fs.readFileSync(afterPath));
if (before.width !== after.width || before.height !== after.height) {
  console.log(JSON.stringify({
    ok: false,
    reason: 'dimension-mismatch',
    before: { w: before.width, h: before.height },
    after:  { w: after.width,  h: after.height },
  }));
  process.exit(0);
}
const { width, height } = before;
const diff = new PNG({ width, height });
const changed = pixelmatch(before.data, after.data, diff.data, width, height, {
  threshold, alpha: 0.4, includeAA: false,
});
fs.writeFileSync(diffPath, PNG.sync.write(diff));
const total = width * height;
const pct = (changed / total) * 100;
console.log(JSON.stringify({
  ok: true,
  width, height, total, changed,
  changed_pct: +pct.toFixed(3),
  diff_path: diffPath,
  threshold,
}));
