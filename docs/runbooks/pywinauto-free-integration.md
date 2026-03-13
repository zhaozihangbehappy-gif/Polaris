# pywinauto Free Integration

## Purpose

This runbook records the integration of `pywinauto` as a free Windows-standard-control capability inside the broader Windows GUI generalization project.

## Policy fit

- open source
- local
- no paid dependency
- useful for standard Windows controls and UI Automation paths

## Current executable entrypoints

- `scripts/windows/pywinauto_smoke.py`
- `scripts/windows/run-pywinauto-smoke-from-wsl.sh`

## Current scope

- verify `pywinauto` importability on the Windows host
- enumerate desktop windows through UIA backend
- persist structured window evidence to the Windows-side artifact folder

## Why this matters

`pywinauto` should not replace the existing desktop bridge, but it is a strong free addition for standard Windows controls, dialogs, Explorer, and conventional desktop UI.
