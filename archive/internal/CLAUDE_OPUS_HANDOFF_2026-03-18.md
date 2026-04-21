# Polaris Opus Handoff

You are continuing a partially completed Claude session in a fresh conversation.

## Workspace

- Project root: `/home/administrator/.openclaw/workspace/projects/polaris-skill/Polaris`
- Previous Claude session transcript: `/home/administrator/.claude/projects/-mnt-c-Users-Administrator/4b9496ad-7641-4954-a61c-6a208949e764.jsonl`

## Total Mission

Continue the Polaris release-readiness work described in `RELEASE_PLAN.md`.

The mission is not architecture work. The mission is to push the experience packs to release quality:

1. Build and validate fixture coverage.
2. Expand and correct experience pack patterns.
3. Verify first-hit performance.
4. Verify reproduction cases.
5. Make a clear release judgment based on the documented gates.

## Important Constraints

- Stay in this project directory, not `/mnt/c/Users/Administrator`.
- Use model `opus`.
- Do not assume the old conversation is still reliable; recover from files and current repo state.
- Be explicit about what is already done, what is proven, and what is still missing.
- Prefer smaller, focused verification commands over one huge long-running command that may time out.
- Do not use giant inline shell payloads like `python3 -c "....many lines...."` for diagnostics.
- If a diagnostic needs real logic, write or use a script file and run that file.
- Prefer commands that finish in under 30 seconds.

## What Is Already Done

These files were created or updated in the interrupted work and are present in the repo:

- `RELEASE_PLAN.md`
- `scripts/verify-firsthit.sh`
- `scripts/verify-reproductions.sh`
- many files under `experience-packs/`

Current repo state already contains many modified and untracked files. Do not discard them.

## Proven Intermediate Results

From the interrupted work, the first-hit verification already produced this result:

- P0 kill gate ecosystems all passed on holdout:
  - python: 8 / 10 = 80%
  - node: 10 / 10 = 100%
  - docker: 8 / 10 = 80%
- Additional ecosystems that reached holdout >= 60%:
  - java: 9 / 10 = 90%
  - rust: 7 / 10 = 70%
- Ecosystems below threshold:
  - go: 5 / 10 = 50%
  - ruby: 3 / 10 = 30%
  - terraform: 3 / 10 = 30%

The interrupted session concluded:

- P0 kill gate passed.
- 5 ecosystems currently meet the holdout threshold.
- The next critical problem is reproduction verification, not first-hit.

## Environment Reality

At the time of interruption, the environment check showed only these runtimes are available:

- python3
- node

Not available:

- docker
- go
- rust
- java
- terraform
- ruby

This means reproduction validation must be handled carefully:

- python/node failures can be debugged directly in this environment.
- the other ecosystems may require shell-simulated or environment-agnostic reproduction strategy consistent with the release plan, or a documented release-risk decision if direct validation is impossible.

## Last Clear Working Position

The previous session had already made this judgment:

"Now the key problem is reproduction verification. The environment only has python3 and node. The other six ecosystems do not have runtimes available. Per the plan, rewrite them using a shell-simulated strategy, while also fixing the python/node failure items."

Then it switched to smaller-step debugging because long commands were timing out.

## Python Reproduction Status Already Observed

The previous session's focused python check reported:

- `Python: 21 pass, 7 fail`

It specifically listed these failures:

- `build_error.json[0]: trigger_no_error | Missing Python.h header — python3-dev package like`
- `build_error.json[2]: trigger_no_error | Wheel build failed — likely missing system build d`
- `encoding_error.json[0]: trigger_no_error | Unicode decode error — force UTF-8 IO encoding and`
- `encoding_error.json[2]: trigger_no_error | File contains non-UTF-8 bytes — set locale to C.UT`
- `missing_dependency.json[3]: trigger_no_error | pip cannot find package — ensure pip index URL is`
- `resource_exhaustion.json[0]: trigger_exc: Command 'python3 -c "x = bytearray(1); exec('x = x * 2\n' * 40)" 2>&1 || true' timed out after 10 seconds`
- `version_conflict.json[1]: trigger_no_error | pip dependency resolution conflict — cannot resolv`

## Node Reproduction Status

The previous session started a focused node reproduction check next, but that step was interrupted before a useful result was recorded.

## Required Recovery Procedure

Before making new edits:

1. Read `RELEASE_PLAN.md`.
2. Read `scripts/verify-firsthit.sh`.
3. Read `scripts/verify-reproductions.sh`.
4. Check `git status`.
5. Read the previous transcript file only as needed to recover context.
6. Summarize:
   - total mission
   - proven progress
   - exact next step

## Exact Next Step

Resume from here:

1. Reproduce the current repo state.
2. Re-run focused reproduction diagnostics for python and node in small chunks.
   Use `python3 scripts/repro_diag.py python` and `python3 scripts/repro_diag.py node`.
3. Fix python reproduction failures first.
4. Then fix node reproduction failures.
5. Then evaluate how to handle the other six ecosystems in a release-honest way under the current runtime limitations.
6. End with a clear release-readiness assessment against `RELEASE_PLAN.md`.

## Output Style

Work like a senior engineer doing a careful recovery after an interrupted run:

- state what is known versus inferred
- prefer concrete file-backed evidence
- avoid redoing broad expensive searches unless necessary
- keep momentum

Begin by confirming the recovery point and then continue the work.
