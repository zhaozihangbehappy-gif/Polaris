# GUI Regression Run Procedure

## Goal

Turn the GUI regression matrix into a repeatable execution path with saved evidence.

## Current executable path

Use:

```bash
python3 scripts/gui/run_gui_regression.py
```

Environment variables expected:

- `OPENCLAW_DESKTOP_KEY`
- optional `OPENCLAW_DESKTOP_BASE_URL`
- optional `OPENCLAW_DESKTOP_AUTH_HEADER`
- optional `OPENCLAW_DESKTOP_TIMEOUT_SECONDS`

## Current implemented scenarios

### G1 — baseline fixed layout
The runner currently implements:
- window enumeration
- Blender-window signature match
- activate target window
- capture target window
- foreground-verified center move
- evidence persistence to `artifacts/gui-regression-runs/<run-id>/`

### G5 — repeated-run stability
The runner also implements a first repeated-run scenario:
- repeats the bounded baseline path multiple times
- stores per-attempt evidence
- defaults to `--repeats 3`

## Output files

Each run writes:
- `manifest.json`
- `windows.json`
- `g1-baseline.json` when G1 executes successfully
- `g5-repeated-runs.json` when G5 executes successfully
- `error.txt` when the run fails

## Shortest path forward

Implement next in this order:
1. G5 repeated-run stability
2. G2 moved-window validation
3. G3 resized-window validation
4. G4 focus-loss safe-fail validation
5. G6 DPI/scaling validation

## Promotion rule

Do not mark GUI automation as stable until:
- G1 passes consistently
- G5 passes 3 consecutive runs
- G2 and G3 pass in the target environment
- focus-loss handling fails safe or recovers deterministically
