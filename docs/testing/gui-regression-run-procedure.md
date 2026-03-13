# GUI Regression Run Procedure

## Goal

Turn the GUI regression matrix into a repeatable execution path with saved evidence.

## Current executable paths

### Single scenario runner

```bash
python3 scripts/gui/run_gui_regression.py
```

### Full regression wrapper

```bash
scripts/gui/run_full_gui_regression.sh
```

Environment variables expected:

- `OPENCLAW_DESKTOP_KEY`
- optional `OPENCLAW_DESKTOP_BASE_URL`
- optional `OPENCLAW_DESKTOP_AUTH_HEADER`
- optional `OPENCLAW_DESKTOP_TIMEOUT_SECONDS`

## Current implemented scenarios

### G1 — baseline fixed layout
- window enumeration
- Blender-window signature match
- activate target window
- capture target window
- foreground-verified center move

### G2 — moved-window validation
- move Blender window to a new screen position
- re-enumerate and confirm new rect
- rerun bounded baseline path

### G3 — resized-window validation
- resize Blender window
- re-enumerate and confirm new rect
- rerun bounded baseline path

### G4 — focus-loss validation
- steal focus to another window
- attempt a foreground-verified move
- expect a safe block or safe-fail signal
- refresh Blender window and run bounded recovery path

### G5 — repeated-run stability
- repeat the bounded baseline path multiple times
- store per-attempt evidence
- default `--repeats 3`

## Output files

Each run writes:
- `manifest.json`
- `windows.json`
- `g1-baseline.json` when G1 executes successfully
- `g2-moved-window.json` when G2 executes successfully
- `g3-resized-window.json` when G3 executes successfully
- `g4-focus-loss.json` when G4 executes successfully
- `g5-repeated-runs.json` when G5 executes successfully
- `error.txt` when the run fails

## Promotion rule

Do not mark GUI automation as stable until:
- G1 passes consistently
- G5 passes 3 consecutive runs
- G2 and G3 pass in the target environment
- G4 focus-loss handling fails safe or recovers deterministically
