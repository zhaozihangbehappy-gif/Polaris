# Blender Bridge Startup Runbook

## Purpose

This runbook describes the Blender-side bridge from an operational perspective: what it is for, how to bring it up, and how to confirm it is the right tool for a given action.

## What the Blender bridge is for

The Blender bridge exists so the automation stack can perform structured scene operations without relying on fragile UI clicking.

It should own operations where exact state matters.

Typical Blender-bridge responsibilities include:

- object inspection
- transform reads and writes
- scripted geometry creation
- selection and collection management
- render/export orchestration
- structured results back to the caller

## Role relative to desktop bridge

The two bridges are complementary:

### Desktop bridge
Use for:
- finding and activating Blender
- validating visible UI operability
- navigating desktop/native UI surfaces
- collecting screenshot evidence

### Blender bridge
Use for:
- manipulating scene state precisely
- querying state for assertions
- generating or editing geometry deterministically
- repeatable export and render workflows

## Before startup

Confirm:

1. Blender is installed and can launch normally
2. the required OpenClaw Blender-side addon / bridge component is available
3. the desktop bridge is available too if hybrid operation is expected
4. the intended `.blend` file or scene context is known

## Startup checklist

Because the exact addon and host wiring can evolve, keep the startup checklist intent-focused:

1. launch Blender
2. enable the OpenClaw Blender bridge/addon if not already enabled
3. start or activate the Blender bridge runtime inside Blender
4. confirm the bridge is listening/responding through its expected local path
5. run a harmless structured query, such as reading scene or object metadata

## Minimal health check

A startup is considered minimally healthy if:

- Blender is open and responsive
- the bridge reports online / available
- a simple query succeeds
- a simple write/read-back cycle succeeds

Examples of good smoke tests:

- query current scene name
- read selected object names
- read active object transform
- set a temporary transform value and read it back in a controlled scene

## Recommended startup order in hybrid workflows

1. start desktop bridge
2. open Blender
3. start Blender bridge
4. confirm desktop bridge sees Blender window
5. confirm Blender bridge can read scene state
6. proceed with workflow using the correct boundary per action

## Common failure modes

### 1. Addon not enabled

Symptoms:
- bridge appears unavailable
- no response from Blender-side runtime

### 2. Blender is open but bridge not started

Symptoms:
- window automation works
- structured scene commands fail

### 3. UI and scene state drift apart

Symptoms:
- a desktop action visually happens
- expected scene state is not reflected in bridge query results

This is exactly why scene assertions should prefer Blender API queries.

### 4. Wrong tool chosen for the job

Symptoms:
- brittle click-heavy flows for deterministic tasks
- hard-to-replay failures
- poor validation quality

Mitigation:
- move exact state edits and assertions into Blender scripts
- reserve desktop actions for mode entry, visibility checks, and UI-only flows

## Practical operator rule

If the task can be expressed as:

- "set"
- "get"
- "create"
- "inspect"
- "export"

then first ask whether it should be a Blender bridge call instead of a desktop action.

## Recommended future additions

- exact addon enablement steps
- bridge startup command sequence inside Blender
- reference smoke-test script for object transform round-trip validation
- standard scene fixtures for regression checks
