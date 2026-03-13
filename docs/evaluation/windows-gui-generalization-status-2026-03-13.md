# Windows GUI Generalization Status — 2026-03-13

## Purpose

This document archives the current state of the Windows GUI generalization effort before moving on to the next problem.

It is meant to preserve:
- what has already been built
- what was actually proven
- what still hurts
- the current honest score

## Current high-level conclusion

The project has moved beyond isolated GUI scripts and now has the beginnings of a local execution stack:

- calibrated GUI templates
- local Windows macro execution
- bridge-based verification
- a first local GUI state machine

However, the system is not yet fully smooth for arbitrary long-chain Windows GUI work.

## Current score

For the strict standard:

- long tasks
- heavy use of Windows GUI generalization
- fully visible mouse trajectories
- reduced stop/start thinking

Current score:

- **78 / 100**

## Why it is already strong

### Visible execution rules are now explicit
- all clicks should use visible trajectories
- drag should keep multi-frame evidence
- long GUI chains should avoid instant jump points

### Core local execution layers now exist
- desktop bridge
- GUI regression runner
- GUI template system
- local macro runner
- first local GUI state machine

### Verified template paths
- `explorer_open_file` — pass
- `file_dialog_select_file` — pass
- `blender_focus` — pass

### Verified local scenario path
- `delivery_open_and_focus` — pass

## What was actually built

### 1. Local GUI macro runner
- `scripts/windows/gui_macro_runner.ps1`
- `scripts/windows/run-gui-macro-from-wsl.sh`

Purpose:
- run longer GUI action chains locally on Windows
- reduce cloud-side micro-planning between tiny steps
- preserve visible mouse trajectories while improving continuity

### 2. GUI template system
- `scripts/windows/gui_template_builder.py`
- `scripts/windows/gui_template_orchestrator.py`
- `docs/runbooks/gui-template-system.md`

Purpose:
- discover target windows/regions with `pywinauto`
- build calibrated plans
- execute those plans locally
- verify state after execution

### 3. Local GUI state machine
- `scripts/windows/gui_state_machine.py`
- `docs/runbooks/gui-state-machine.md`

Current scenario:
- `delivery_open_and_focus`
  - `explorer_open_file`
  - `blender_focus`

## Main pain points still remaining

### 1. Thinking is not yet localized deeply enough
The system has started to localize execution, but not enough of the long-chain state progression has been moved local.

Current reality:
- some known paths are smoother
- new paths still trigger extra cloud-side thought and re-planning

### 2. Template coverage is still thin
The current template set is useful but narrow.

That means:
- known tasks are improving
- unfamiliar tasks still slow down noticeably

### 3. Calibration/discovery still costs too much
Time is still lost on:
- identifying the right host window
- handling duplicate windows
- choosing UIA vs win32 backends
- dealing with shell/encoding/process quirks

### 4. Recovery is not yet deeply state-machine-native
Recovery notes and playbooks exist, but many recovery decisions are not yet part of a richer local state engine.

### 5. Verification is better, but not yet minimal-friction everywhere
Execution and verification are now connected, but not yet uniformly cheap or elegant across all paths.

## Most important technical insight from this round

The fundamental problem is not just mouse speed.

The bigger issue is:

- cloud-side stop/start thought between many small GUI actions

So the correct direction is not merely:
- faster cursor movement

It is:
- local calibrated templates
- local continuous action execution
- local state progression
- cloud-side involvement only at higher-level decision points

## Current architectural direction

### Localize the following
- calibration
- common action chains
- state transitions
- recovery branches
- evidence persistence

### Keep cloud-side for
- goal selection
- unusual exception handling
- new strategy changes
- non-routine interpretation

## What should happen next when this topic resumes

Priority order:

1. expand the template library
2. deepen the local state machine
3. cache/reuse calibration knowledge
4. make recovery paths template-native
5. reduce repeated discovery work across long chains

## Bottom line

This problem is no longer in the "concept only" stage.

A first real local GUI execution stack now exists.

But the remaining gap to a truly smooth long-chain Windows GUI operator is still mostly about:

- local state progression
- template breadth
- discovery/calibration friction

That is the right place to continue next time.
