# Repository Scope

## What this repo is for

This repository tracks project-facing material that is safe and useful to sync:

- project summaries
- prompts
- validation scripts
- architecture notes
- runbooks

## What this repo is not for

This repository should not store:

- private memory or personal profile files
- transient runtime state
- local-only machine details that are not needed for collaborators
- bulky binary artifacts unless there is a clear reason

## Current tracked files

- `README.md`
- `.gitignore`
- `projects/blender-cabinet-12cell/README.md`
- `prompts/codex-blender-desktop-agent-formal.txt`
- `trajectory-proof.ps1`
- `docs/architecture/overview.md`
- `docs/runbooks/github-auth.md`
- `docs/runbooks/repo-scope.md`

## Current external artifact boundary

For the cabinet project, the canonical delivery folder currently lives outside this repo on the Windows side:

- `D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\delivery\`

That folder currently contains the richer delivery payload, including screenshots, parameter summaries, and the Blender source file.

## Recommended next cleanup

1. add a manifest listing the external delivery files
2. decide whether this repo should later absorb selected non-private docs from the Windows-side delivery folder
3. keep `.gitignore` conservative until repository structure stabilizes
