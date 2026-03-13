# GUI Template System

## Purpose

Unify three layers of the Windows GUI generalization project:

- `pywinauto` for control/region discovery and calibration
- local Windows macro execution for smooth continuous action
- desktop bridge for verification and evidence

## Current template kinds

- `explorer_open_file`
- `explorer_select_file`
- `blender_focus`
- `file_dialog_select_file`

## Entrypoints

- Windows-side builder: `scripts/windows/gui_template_builder.py`
- WSL-side orchestrator: `scripts/windows/gui_template_orchestrator.py`
- local macro executor: `scripts/windows/gui_macro_runner.ps1`

## Design

1. discover target regions with `pywinauto`
2. build a local macro plan with calibrated points
3. execute the plan continuously on Windows
4. verify target state with desktop bridge when applicable

This is the current path toward reducing cloud-side micro-planning between tiny GUI actions.
