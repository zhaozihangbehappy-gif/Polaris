# Playwright Free Integration

## Purpose

This runbook records how Playwright's free, local browser-automation capability is integrated into the repository without introducing any paid dependency.

## Policy

- use only Playwright's free local capability
- do not depend on paid SaaS wrappers or paid visual/browser layers
- if a missing feature later requires money, do not adopt that paid layer; build the missing piece locally instead

## Current executable entrypoints

- `scripts/browser/playwright_smoke.js`
- `scripts/browser/run_playwright_smoke.sh`

## What is currently covered

- local Chromium install through Playwright
- headless browser launch
- page navigation
- screenshot capture
- page title capture
- lightweight DOM proof (`h1` extraction when available)
- evidence persistence under `artifacts/browser-runs/`

## What this is for

This is the browser-GUI branch of the broader execution layer.

Use Playwright for:
- websites
- web apps
- browser login flows that do not require paid tooling
- page-state assertions
- structured browser screenshots and evidence

Do not use Playwright as a substitute for native Windows desktop GUI automation.

## Why this belongs in the weapon stack

Playwright is one of the strongest free browser automation tools available and complements the existing Windows desktop bridge rather than replacing it.
