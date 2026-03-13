# Blender / Desktop Validation Runbook

## Purpose

This runbook records the practical validation path for the local Windows desktop automation chain and Blender-side bridge.

It is meant to preserve the implementation process, not just the final result.

## Validation goal

Prove that:

1. the desktop bridge can discover and activate the Blender window
2. desktop input can be injected into the correct foreground target
3. screenshots can be captured during execution
4. Blender state can be changed through real GUI input
5. Blender bridge can coexist with desktop-driven control

## Environment shape

- Windows host running desktop bridge on `http://127.0.0.1:7788/`
- Blender 5.0 GUI window present
- Blender window class expected: `GHOST_WindowClass`
- local authorization header used by the proof script:
  - `x-openclaw-desktop-key: desktop-secret`

## What was validated

The control chain was validated with:

- window enumeration
- Blender window selection by title and class
- window activation
- capture of start / intermediate / end frames
- mouse movement across multiple planned points
- final click at the end of the path

Separately, a stronger functional proof was also established earlier through:

- activating Blender
- issuing `g`
- moving the mouse
- confirming with left click
- verifying object location changed from `[0,0,0]` to `[-0.9715548753738403, 4.465816497802734, 5.407055854797363]`

That result matters more than a pure cursor-motion proof because it shows actual application state change.

## Proof script in repo

- `trajectory-proof.ps1`

## What the script does

1. POSTs to `window.inspect` with `action=list`
2. finds a Blender 5.0 top-level window with class `GHOST_WindowClass`
3. extracts hwnd and rect
4. computes four waypoint coordinates inside the Blender window
5. activates the target window
6. captures an initial frame
7. moves the mouse through four points with foreground verification enabled
8. captures frames after each move
9. performs a final click
10. captures a final frame

## Key safety characteristics in the script

- window-bound selector via `hwnd`
- `verifyForeground = $true`
- `abortKey = "esc"`
- bounded timeout on HTTP calls
- explicit failure if Blender window is not found

## Success criteria

A run is considered successful if:

- Blender window is found and activated
- no foreground verification failure occurs
- image captures are returned at each stage
- desktop input calls succeed without target mismatch
- resulting screenshots show cursor progression in Blender
- for functional proof runs, Blender scene state changes as expected

## Recommended next validation additions

- capture and archive returned JSON responses as structured evidence
- add a Blender bridge validation script that queries object transform before and after GUI actions
- define a repeatable smoke test for startup: desktop bridge + Blender bridge + one desktop action + one Blender API action
