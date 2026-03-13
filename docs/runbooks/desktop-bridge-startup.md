# Desktop Bridge Startup Runbook

## Purpose

This runbook describes how to think about, start, and validate the Windows desktop bridge used for desktop automation.

It is written as an operational guide rather than a code spec.

## What the desktop bridge is responsible for

The desktop bridge provides desktop-native capabilities such as:

- window discovery and activation
- screen capture
- mouse movement and click injection
- drag and hotkey execution
- foreground verification and action guarding

It should be treated as the desktop-side actuator and observer.

## Expected endpoint shape

The current proof scripts assume a local HTTP surface similar to:

- `http://127.0.0.1:7788/`

Observed endpoint families include:

- `window.inspect`
- `desktop.capture`
- `desktop.input`

## Expected local auth shape

Example request header used in the proof script:

- `x-openclaw-desktop-key: <secret>`

Do not commit real secrets into Git. Keep them in local environment or local-only config.

## Before startup

Confirm these prerequisites:

1. the Windows host is the machine where desktop automation should occur
2. Blender is installed if Blender-targeted validation is planned
3. no conflicting focus-stealing workflows are active
4. the operator knows the abort key path (`esc` in current examples)
5. the local desktop bridge secret is available to the process that will call the bridge

## Startup checklist

Because the exact host-side launcher may evolve, keep the checklist capability-oriented:

1. start the Windows-side desktop bridge service/process
2. confirm it binds to the expected localhost port
3. confirm requests can be authenticated
4. list windows through `window.inspect`
5. identify the intended target window before injecting input

## Minimal health check

A startup is considered minimally healthy if all of the following are true:

- HTTP requests to the bridge return successfully
- `window.inspect action=list` returns window metadata
- a target application window can be found by title/class
- `desktop.capture` succeeds for the target
- a harmless `desktop.input` action can run with foreground verification enabled

## Recommended startup sequence for Blender work

1. start desktop bridge
2. start Blender
3. ensure Blender UI is fully visible
4. enumerate windows and confirm the Blender window signature
5. capture one baseline frame
6. only then begin active input injection

## Common failure modes

### 1. Bridge not reachable

Symptoms:

- connection refused
- timeout
- no response from localhost endpoint

Likely causes:

- bridge process not running
- wrong port
- local firewall or binding issue

### 2. Auth failure

Symptoms:

- request rejected
- unauthorized response

Likely causes:

- wrong header name
- wrong secret value
- missing secret in caller environment

### 3. Window not found

Symptoms:

- Blender window missing from enumeration
- script throws when trying to select window

Likely causes:

- app not open yet
- title mismatch
- class mismatch
- app still starting up

### 4. Foreground verification failure

Symptoms:

- input rejected despite valid coordinates

Likely causes:

- another app stole focus
- target window not activated
- user interference during automation

### 5. Capture works but input has no effect

Likely causes:

- wrong target window
- coordinates inside a non-interactive region
- modal dialog blocking input path
- app state inconsistent with planned operation

## Operational guidance

- keep `verifyForeground` enabled by default
- prefer window-handle targeting over blind screen coordinates
- capture before and after meaningful actions
- use desktop automation to establish operability, then hand off exact scene operations to Blender API where possible

## Recommended future additions

- exact startup command once host-side service layout stabilizes
- sample curl/PowerShell health checks
- a structured JSON health probe script that archives diagnostics
