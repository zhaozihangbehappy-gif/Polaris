# GUI State Machine

## Purpose

This layer reduces cloud-side stop/start thinking by composing calibrated GUI templates into a local scenario runner.

## Current scenario

- `delivery_open_and_focus`
  - `explorer_open_file`
  - `blender_focus`

## Entry point

```bash
python3 scripts/windows/gui_state_machine.py delivery_open_and_focus
```

## Output

- `artifacts/gui-state-runs/<scenario>-<run-id>.json`
