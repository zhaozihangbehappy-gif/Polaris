# Implementation History

## Purpose

This document turns scattered progress into a compact engineering timeline so the repository preserves not only the current state, but also how the capability stack was built.

## Timeline

### 2026-03-11 — identity, workspace, and direction setting

Initial local workspace identity and user-profile scaffolding was established.

Key direction became clear:

- prefer formal, production-grade local automation
- accept complexity and learning cost
- optimize for a reusable long-term capability stack
- prioritize Windows desktop agent + Blender integration

### 2026-03-12 — Codex / ACP path stabilized

A practical execution pattern was established for longer implementation tasks:

- main session handles planning, review, and orchestration
- Codex CLI acts as executor
- tmux-backed observation windows were used to preserve visibility into ongoing execution where thread binding was not available in the current chat environment

This was important operationally because visible execution was a user preference, not just a technical convenience.

### 2026-03-12 — local Codex / ACP foundation validated

The local OpenClaw ACP / ACPX path was brought up successfully.

Validated points included:

- ACP / ACPX enabled
- user-side `acpx` and `@openai/codex` installed
- Codex CLI authenticated and usable with `gpt-5.4`
- non-interactive `codex exec` identified as a more stable execution path than relying on TUI-only flows

### 2026-03-12 — desktop bridge integration path clarified

A review of the desktop bridge skeleton and upstream structure clarified repository boundaries:

- the local skeleton repository was not the full upstream host
- it should not be treated as the place to fake the main host entrypoint
- the true host wiring path belonged to `openclaw-upstream`

At the same time, a smaller patch set in the skeleton area was implemented and validated:

- `register-desktop-tools.ts` received `baseUrl` trimming and null protection
- associated tests were added
- a temporary TypeScript execution path through Node 22 stripping confirmed passing tests

### 2026-03-12 — upstream capability chain audit completed

A read-only audit of `openclaw-upstream` confirmed that the broader technical chain already existed in partial form:

- host tool creation path
- desktop tools
- bridge client
- Python bridge
- Blender addon
- skill layer

The remaining gap was not raw feasibility, but closure around:

- configuration entrypoints
- host-level default usability
- contract boundaries
- regression validation

The adopted implementation sequence became:

- Patch A: capability contract closure
- Patch B: host tool-system wiring
- Patch C: local bridge and Blender runtime landing
- Patch D: desktop safety and regression validation

### 2026-03-12 — real Windows desktop + Blender control validated

A major milestone was achieved: the Windows desktop bridge and Blender bridge were both proven in a real GUI path.

Validated actions included:

- window activation
- hotkeys
- move
- click
- drag
- multi-frame screenshot evidence

The strongest proof was a real Blender scene-state change driven through desktop input:

- issue `g`
- move mouse
- confirm with left click
- object location changed from `[0,0,0]` to `[-0.9715548753738403, 4.465816497802734, 5.407055854797363]`

That established that desktop input was not merely moving a cursor, but actually driving Blender state.

### 2026-03-12 — 12-cell cabinet concept delivered

Under the design constraint of using only two mold-part families, a rectangular 12-cell cabinet concept was completed and archived in the external Windows delivery folder.

Delivered scope included:

- 2-row x 6-column cabinet layout
- Part A horizontal plate
- Part B vertical template repeated five times
- slots
- lighten windows
- stop features
- exploded view
- dimension notes
- presentation cameras
- exported image set
- Blender source file

This established a concrete production-oriented design artifact, not just infrastructure work.

### 2026-03-13 — repository formalization and Git sync

The local workspace was converted into a cleaner project-facing Git repository.

Actions completed:

- `.gitignore` created to exclude private memory and runtime state
- first project-safe local commit created
- GitHub remote created and bound
- initial push completed
- remote later migrated from HTTPS to SSH
- GitHub SSH over port 443 configured due to blocked port 22
- repository README, architecture docs, runbooks, config examples, and artifact index were added and pushed

## Current state summary

The repository now serves as a clean engineering record for:

- project summaries
- formal prompts
- validation scripts
- architecture decisions
- operational runbooks
- example config structures
- external artifact indexing

## Recommended next history updates

Append this file whenever one of the following happens:

- a new bridge capability is implemented
- a startup or validation path changes materially
- a major Blender-side scripted workflow lands
- an external artifact set becomes stable enough to index or partially import
