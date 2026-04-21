# Authoring Report (v4)

> Snapshot notice (2026-04-21): this file is an authoring-pipeline snapshot, not the live A/B/D authority. Its numbers describe what the authoring batch wrote or skipped at that time. For current release numbers, use `POLARIS_V4_TRUTH_TABLE.md`, backed by a fresh rerun of `scripts/pattern_validator_v4.py`. Do not cite this file and the truth table together as numeric sources.

Generated: 2026-04-20
Source: `authoring_report.json`
Script: `scripts/author_fixtures.py`

## Targets and outcomes

| Metric | Value |
|---|---:|
| authoring_total_targets | 363 |
| authored_fixture_candidate (sandbox-valid) | 48 |
| skipped_already_authored (from pilot) | 3 |
| authoring_failed | 312 |
| sandbox_valid_total_on_disk | 51 |

`sandbox_valid_total_on_disk` includes the 3 pilot rows written before the
full batch (`python.build_error.{000,001,002}`), so it is the ground-truth
count that downstream case generation and validator see.

## Sandbox-valid authored fixtures by ecosystem

| Ecosystem | Sandbox-valid | Pool patterns in ecosystem |
|---|---:|---:|
| python | 24 | 148 |
| node | 20 | 145 |
| rust | 4 | 70 |
| **total** | **48** | **363** |

(The pilot adds +3 to python, for the 27 python / 20 node / 4 rust = 51 on-disk total.)

## Authoring failure breakdown

| Reason | Count |
|---|---:|
| codex_rate_limited | 305 |
| timeout (>300s) | 6 |
| sidecar_parse_failed (authored.json missing/invalid) | 1 |
| synthetic_echo_rejected | 0 |
| pre_failure_not_reproduced | 0 |
| post_fix_failed | 0 |
| reviewer_record_missing | 0 |

No authored fixture reached sandbox with a synthetic recipe, a post-fix fail,
or a missing reviewer record. Every rejection before sandbox was on upstream
Codex execution (rate-limit or timeout), not on fixture quality.

## Validation contract each sandbox-valid row satisfied

For every one of the 51 rows:

1. Codex wrote a real project into the workdir plus `authored.json`.
2. `authored.json` required keys present: `verification_command`,
   `expected_stderr_regex`, `files[]`, `reference_fix_files[]`.
3. A fresh `/tmp/polaris_authoring_sandbox/<pid>/pre` dir was built from
   `files[]`. `verification_command` run → exit code ≠ 0 and stderr matched
   `expected_stderr_regex`.
4. A fresh `/tmp/polaris_authoring_sandbox/<pid>/post` dir was built from
   `files[]` overlaid with `reference_fix_files[]`. Same
   `verification_command` run → exit code = 0.
5. SHA-256 hashes recorded for both dirs in `reviewer_record`.

Any record that did not meet steps 3+4 was marked `sandbox_invalid` and NOT
written into the shard. No rows reached that bucket — fixtures that passed
Codex either reached full validity or never produced `authored.json`.

## Why authoring stopped early

Codex (free tier) usage cap hit at 15:35-ish local time (`You've hit your
usage limit ... try again at 3:46 PM`). All 13 in-flight sessions returned
`turn.failed` and later launches short-circuited, producing
`codex_rate_limited = 305`. The authoring batch was killed cleanly; no
partial/contaminated fixture reached a shard.

## Per-ecosystem tooling coverage

| Ecosystem | Patterns | Toolchain in env | Status |
|---|---:|---|---|
| python | 148 | ✅ python3 | sandboxable |
| node | 145 | ✅ node | sandboxable |
| rust | 70 | ✅ cargo/rustc | sandboxable |
| go | 78 | ❌ | authoring_blocked_tooling_unavailable |
| java | 71 | ❌ | authoring_blocked_tooling_unavailable |
| ruby | 30 | ❌ | authoring_blocked_tooling_unavailable |
| docker | 121 | ❌ | authoring_blocked_tooling_unavailable |
| terraform | 34 | ❌ | authoring_blocked_tooling_unavailable |

Sandboxable total = 363. Tooling-blocked total = 334. See
`TOOLING_BLOCKERS_REPORT.md` for install/fallback options.
