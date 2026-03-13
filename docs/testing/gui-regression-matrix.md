# GUI Regression Matrix

## Purpose

Window GUI reliability is a first-class requirement.

This matrix defines the minimum scenarios required before calling desktop automation stable at a production level.

## Core principle

A single successful demo is not enough.

GUI automation must remain accurate under ordinary variation in:
- window position
- window size
- focus state
- scaling / DPI
- UI interruption
- workspace layout

## Priority order

### Priority 1 — must validate first
1. window discovery by title/class
2. foreground activation reliability
3. window-relative coordinate stability
4. capture-before / capture-after evidence
5. abort-path reliability

### Priority 2 — must validate next
1. different Blender window sizes
2. different window positions
3. focus stolen mid-run
4. repeated runs in the same session

### Priority 3 — required for near-100/100 confidence
1. DPI / scaling variation
2. multi-monitor placement
3. modal dialog interruption
4. workspace layout drift
5. recovery after bridge restart or Blender restart

## Regression scenarios

### Scenario G1 — baseline fixed layout
- Blender in expected size and location
- known workspace layout
- no interruptions
- expected result: all core actions pass

### Scenario G2 — moved window
- Blender moved to a different screen position
- expected result: window-relative actions still pass

### Scenario G3 — resized window
- Blender resized smaller or larger
- expected result: coordinate computation still lands in valid regions

### Scenario G4 — focus stolen
- another app takes foreground before action completion
- expected result: foreground verification blocks unsafe action or recovery path triggers

### Scenario G5 — repeated-run stability
- same action repeated at least 3 times
- expected result: no degradation or drift

### Scenario G6 — DPI/scaling variation
- non-default Windows scaling
- expected result: targeting logic remains valid or test fails explicitly with a known reason

### Scenario G7 — modal interruption
- popup or modal overlay appears unexpectedly
- expected result: action is blocked, detected, or recovered safely

### Scenario G8 — workspace layout drift
- Blender UI layout differs from the expected baseline
- expected result: window-only actions still work; control-specific actions either adapt or fail safely

## Evidence required per scenario

For every scenario capture:
- scenario id
- date/time
- monitor/scaling context
- window rect
- target signature used
- screenshots
- command responses
- pass/fail
- recovery path if used

## Pass threshold

A GUI action path should not be called stable unless:
- baseline passes
- moved-window passes
- resized-window passes
- repeated-run passes 3 consecutive runs
- focus-loss behavior is safe

For near-100/100 confidence, DPI and interruption scenarios must also pass or fail safely with deterministic recovery.

## Shortest implementation path

### Step 1
Automate G1 through G5.

### Step 2
Store evidence and classify failures by cause.

### Step 3
Add DPI and modal scenarios.

### Step 4
Promote stable selectors and recovery sequences into reusable state folders.

## Bottom line

If this matrix is not implemented, GUI automation can be impressive but still not production-grade.
