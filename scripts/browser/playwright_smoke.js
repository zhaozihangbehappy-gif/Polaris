#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

function stamp() {
  const now = new Date();
  const pad = (n, w = 2) => String(n).padStart(w, '0');
  return `${now.getUTCFullYear()}${pad(now.getUTCMonth()+1)}${pad(now.getUTCDate())}T${pad(now.getUTCHours())}${pad(now.getUTCMinutes())}${pad(now.getUTCSeconds())}.${pad(now.getUTCMilliseconds(),3)}Z`;
}

async function main() {
  const targetUrl = process.env.PLAYWRIGHT_TARGET_URL || 'https://example.com';
  const runId = stamp();
  const runDir = path.join(process.cwd(), 'artifacts', 'browser-runs', runId);
  fs.mkdirSync(runDir, { recursive: true });

  const manifest = {
    run_id: runId,
    started_at_utc: new Date().toISOString(),
    target_url: targetUrl,
    status: 'running',
    evidence: {},
  };

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    await page.goto(targetUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.screenshot({ path: path.join(runDir, 'page.png'), fullPage: true });
    const title = await page.title();
    const url = page.url();
    const h1 = await page.locator('h1').first().textContent().catch(() => null);

    manifest.status = 'pass';
    manifest.evidence = {
      title,
      url,
      h1,
      screenshot: path.join('artifacts', 'browser-runs', runId, 'page.png'),
    };
  } catch (error) {
    manifest.status = 'fail';
    manifest.error = `${error.name}: ${error.message}`;
    fs.writeFileSync(path.join(runDir, 'error.txt'), manifest.error);
    console.error(manifest.error);
  } finally {
    if (browser) await browser.close();
    manifest.finished_at_utc = new Date().toISOString();
    fs.writeFileSync(path.join(runDir, 'manifest.json'), JSON.stringify(manifest, null, 2));
    console.log(path.join('artifacts', 'browser-runs', runId));
  }

  process.exit(manifest.status === 'pass' ? 0 : 1);
}

main();
