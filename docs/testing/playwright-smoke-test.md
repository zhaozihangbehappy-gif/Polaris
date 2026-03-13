# Playwright Smoke Test

## One-command path

```bash
scripts/browser/run_playwright_smoke.sh
```

## Default target

- `https://example.com`

Override with:

```bash
PLAYWRIGHT_TARGET_URL=https://your-target scripts/browser/run_playwright_smoke.sh
```

## Expected outputs

Each run writes a folder under:

- `artifacts/browser-runs/<run-id>/`

Expected files:
- `manifest.json`
- `page.png`
- optional `error.txt`

## Pass condition

A smoke run passes if:
- Playwright launches Chromium successfully
- the target page loads
- a screenshot is written
- title/url evidence are saved

## Why this matters

This makes the browser-GUI branch executable, evidence-backed, and fully free.
