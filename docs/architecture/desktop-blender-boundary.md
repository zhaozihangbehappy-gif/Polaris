# Desktop Automation vs Blender API Boundary

## Principle

Use desktop automation for what is genuinely desktop-native.
Use Blender Python API for what is fundamentally scene/state-native.

Do not click through Blender UI for operations that need reliability, structure, or exactness.

## Desktop-driven responsibilities

Desktop automation is appropriate for:

- launching or foregrounding Blender
- verifying a Blender window exists and is focused
- navigating menus or modal UI when no stable API path is exposed through the bridge yet
- interacting with transient desktop-native dialogs
- collecting visual evidence from the live UI
- validating that a human-visible workflow can actually be driven end to end
- limited smoke tests of hotkeys, clicks, drags, and viewport interaction

## Blender API responsibilities

Blender scripting should own:

- object creation / deletion
- transform queries and exact transform writes
- scene graph inspection
- selection state reads and writes
- collection management
- mesh generation and parameterized geometry
- camera creation and placement
- render/export orchestration
- dimension metadata generation
- state assertions used by tests

## Why this split matters

Desktop automation is useful for control and proof of operability, but it is:

- focus-sensitive
- layout-sensitive
- vulnerable to modal interruptions
- slower than direct scene manipulation
- less structured in return values

Blender API is better when exact state matters because it is:

- deterministic
- structured
- inspectable
- easier to validate automatically
- more robust to UI drift

## Recommended operating model

### Fast path

1. use window metadata to target Blender
2. use desktop automation only for entering the correct UI mode or confirming visible operability
3. hand off scene operations to Blender bridge scripts
4. read structured results back from Blender

### Slow path / recovery

When bridge operations fail or Blender is in an unexpected UI state:

1. use desktop automation to recover focus and dismiss UI obstacles
2. use capture + inspection to understand the visual state
3. restore a known layout or workspace
4. retry scripted scene operations

## Practical examples

### Should stay desktop-driven
- bring Blender to foreground
- open the correct application window
- validate mouse trajectory / click path in live GUI
- exercise a viewport interaction as an end-to-end proof

### Should move to Blender API
- set object location precisely
- create the cabinet parts and repeated instances
- generate slots and lighten windows
- produce exploded view transforms
- add cameras and export renders in a repeatable way
- inspect object names, transforms, and counts for automated assertions

## Repository implication

This repo should keep both:

- desktop-side proof scripts and runbooks
- design notes for Blender-side scripted operations

That way the project history preserves not just the target architecture, but the actual engineering boundary decisions.
