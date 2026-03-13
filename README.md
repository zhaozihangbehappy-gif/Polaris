# Northern Lights

A local-first engineering workspace for building a production-grade Windows desktop automation stack around OpenClaw and Blender.

## Current tracked contents

- `projects/blender-cabinet-12cell/README.md`
  - project note for the 12-cell cabinet concept and canonical delivery artifacts
- `prompts/codex-blender-desktop-agent-formal.txt`
  - formal implementation prompt for a production-grade Blender desktop agent stack
- `trajectory-proof.ps1`
  - PowerShell proof script for validating desktop input trajectory and Blender window interaction
- `.gitignore`
  - excludes private memory, local runtime state, and machine-specific workspace context

## Why the repo is intentionally small right now

This repository is currently used as a clean project-facing record.

Private or machine-local OpenClaw context is intentionally excluded, including:

- agent identity / persona files
- personal memory files
- runtime state under `.openclaw/`
- local scratch files

That keeps the repository safe to sync while preserving local continuity files on the machine.

## Scope

The current direction is:

1. Windows desktop bridge + Blender bridge capability
2. reliable local automation runtime
3. reusable prompts / scripts / project notes
4. gradual promotion into a more formal engineering repository

## Suggested next additions

- `docs/architecture/`
- `docs/runbooks/`
- `artifacts/` index files or export manifests
- formal test notes for desktop and Blender bridge validation
