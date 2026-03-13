# Architecture Overview

## Purpose

This repository is a clean, project-facing record for a local-first OpenClaw + Windows desktop automation + Blender workflow.

It is intentionally narrower than the full local workspace. Personal memory, agent runtime state, and machine-private context are kept out of Git.

## Current repository layers

### 1. Project notes
- `projects/blender-cabinet-12cell/README.md`

Captures the cabinet concept, the two-part mold-oriented design constraint, and the canonical delivery artifact location on the Windows side.

### 2. Prompts
- `prompts/codex-blender-desktop-agent-formal.txt`

A formal implementation prompt describing the desired production-grade Windows desktop + Blender automation stack.

### 3. Validation scripts
- `trajectory-proof.ps1`

A PowerShell proof script for validating desktop bridge control against a real Blender window.

## Boundary: what is intentionally excluded

Excluded by `.gitignore`:

- `.openclaw/` runtime state
- `MEMORY.md` and `memory/` long-term and daily private notes
- `AGENTS.md`, `SOUL.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`, `HEARTBEAT.md`
- local scratch / placeholder files

This keeps the repository sync-safe while preserving local continuity files in the OpenClaw workspace.

## Suggested growth path

### Near-term
- add runbooks for GitHub auth, desktop bridge validation, and Blender bridge startup
- add architecture notes for desktop bridge / Blender bridge boundaries
- add delivery indexes for external artifact folders

### Mid-term
- promote prompts into implementation specs
- add reproducible validation procedures
- add test evidence manifests and benchmark notes

### Long-term
- split reusable components into a dedicated implementation repo if code volume increases
- keep this repo as the canonical planning / validation / operations record, or evolve it into the main implementation repo depending on where real code lands first
