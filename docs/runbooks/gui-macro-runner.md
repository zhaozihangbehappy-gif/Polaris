# GUI Macro Runner

## Purpose

This runner localizes multi-step GUI execution into a single Windows-side macro run so the agent does not have to re-plan every tiny step from the cloud side.

## Current entrypoint

```bash
scripts/windows/run-gui-macro-from-wsl.sh <plan.json>
```

## Supported step kinds

- `activateExplorerPath`
- `movePath`
- `click`
- `doubleClick`
- `sendKeys`
- `wait`

## Why it exists

The goal is smoother Windows GUI execution:
- visible mouse trajectories remain
- but planning/execution chatter between tiny steps is reduced
- long tasks become more locally continuous
