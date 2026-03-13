# Full GUI Regression Runbook

## One-command path

```bash
scripts/gui/run_full_gui_regression.sh
```

## What it does

1. starts desktop bridge on Windows
2. starts Blender 5.0
3. waits for the GUI to appear
4. runs G1 baseline
5. runs G2 moved-window
6. runs G3 resized-window
7. runs G4 focus-loss
8. runs G5 repeated-run stability

## Expected output

The command prints the run directory, for example:

```text
artifacts/gui-regression-runs/<run-id>
```

Then inspect:
- `manifest.json`
- `windows.json`
- scenario-specific JSON files

## Current default secret path

Unless overridden, the wrapper uses:
- `OPENCLAW_DESKTOP_KEY=desktop-secret`

Override when needed:

```bash
OPENCLAW_DESKTOP_KEY=your-real-key scripts/gui/run_full_gui_regression.sh
```
