# Hybrid Round-Trip Test

## Purpose

This test is the shortest meaningful proof that the hybrid stack is working as intended.

It is not enough to prove:
- the desktop can move a cursor
- Blender can be opened
- a bridge responds somewhere

The hybrid stack is only truly healthy when:

1. a desktop-side action reaches the correct Blender window
2. Blender-side state can then be confirmed through a structured read path
3. the result can be judged pass/fail without guesswork

## Why this matters

This is the bridge between "GUI works" and "the system can be trusted to act precisely."

## Test shape

### Preconditions
- desktop bridge online
- Blender open and visible
- Blender bridge/addon online
- target scene loaded
- target object or test fixture known in advance

### Action path
1. identify Blender window by class/title
2. bring Blender to foreground
3. perform one bounded GUI action
4. read scene state through Blender-side structured query
5. compare against expected result

## Recommended first round-trip

Use a deliberately simple transform change on a known object.

### Candidate flow
1. start from a known test scene
2. ensure target object is selected
3. use desktop automation to enter a move operation in the viewport
4. confirm action through GUI
5. query object transform through Blender-side bridge
6. assert that transform changed from baseline in the expected direction or magnitude band

## Pass criteria

A run passes only if:
- the correct Blender window was targeted
- foreground verification succeeded
- the GUI action completed without modal interruption
- Blender-side query succeeded
- queried state matches the expected postcondition

## Failure categories

### A. window-target failure
- wrong window
- focus stolen
- title/class mismatch

### B. GUI execution failure
- input blocked
- wrong viewport region
- modal interruption
- layout drift

### C. structured-query failure
- Blender bridge offline
- query path broken
- object lookup mismatch

### D. semantic failure
- action executed, but resulting scene state is not what was intended

## Evidence to archive per run

- timestamp
- environment profile
- target window signature
- screenshot before action
- screenshot after action
- Blender-side returned state
- explicit pass/fail reason

## Promotion rule

No Blender workflow should be called stable until this hybrid round-trip test passes repeatedly in the target environment.

## Recommended next implementation

Create a script pair:
- desktop-side action driver
- Blender-side state-query checker

Then store results in a repeatable evidence folder.
