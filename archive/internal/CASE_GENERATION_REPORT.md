# Case Generation Report (v4)

Generated: 2026-04-20
Source: `case-generation-report-v4.json`
Script: `eval/case_generator.py`

## Current counts

| Metric | Value |
|---|---:|
| official_schema_valid_count | 167 |
| candidate_schema_valid_count | 530 |
| total_schema_valid_pool | 697 |
| promotion_eligible_count (= runnable_case_count) | 51 |
| blocked_no_fixture_count | 646 |
| generated hermetic case files | 51 |
| generated skeleton count | 646 |

## Per-pool runnable

| Pool | Runnable cases |
|---|---:|
| official | 51 |
| candidate | 0 |

No candidate has an authored fixture yet — every candidate is blocked on
`missing_authored_fixture`. The previous candidate `shortest_verification`
/ `fix_command` recipes were all synthetic bash-echo and are rejected by
the post-invalidation schema.

## Why the number is 51, not 363 or 697

The case generator now **requires** a pattern-level sandbox-valid
`authored_fixture` block before emitting a runnable case. A case is
generated iff ALL of these hold:

- `authored_fixture.files[]` non-empty and written to disk
- `authored_fixture.verification_command` exits non-zero on the fixture
- `authored_fixture.expected_stderr_regex` matches the failure stderr
- `authored_fixture.reference_fix_files[]` non-empty
- overlaying `reference_fix_files[]` makes the same command exit 0
- `reviewer_record` present with all three sandbox exit codes + stderr-match
  boolean + pre/post workdir SHA-256 hashes

Any pattern still riding on `shortest_verification.command = bash -c 'echo
"..." >&2; exit 1'` is excluded. No synthetic recipe can drive a case.

## Per-ecosystem runnable breakdown

| Ecosystem | Runnable cases |
|---|---:|
| python | 27 |
| node | 20 |
| rust | 4 |
| go | 0 (tooling blocked) |
| java | 0 (tooling blocked) |
| ruby | 0 (tooling blocked) |
| docker | 0 (tooling blocked) |
| terraform | 0 (tooling blocked) |

## Blocked reasons for 646 non-runnable patterns

| Reason | Count |
|---|---:|
| missing_authored_fixture | 646 |
| missing_fix_command | 530 |
| missing_verification_command | 0 |
| missing_expected_stderr | 0 |

`missing_fix_command` still reports 530 because the candidate-pool harvester
never produced one; this is an informational overlap, not an extra blocker.
The binding constraint is `missing_authored_fixture`.

## Where the case files live

- Case JSON: `eval/cases/generated_*.json` (51 files)
- Manifest JSON: `eval/fixtures/<case_id>/manifest.json`
- Fixture files: `eval/fixtures/<case_id>/files/...` (real project contents)
- Skeletons for blocked patterns: `eval/generated-cases-v4/<pool>/<eco>/*.json`
- Cursor manual queue: `eval/runs/manual_cursor_required.json` (102 entries)

## Orchestrator contract

Each generated case has:

- `fixture_strategy = "authored_files"` (hermetic.py copies `files/` into
  the per-variant workdir)
- `expected_failure_command = cd {workdir} && <verification_command>`
- `success_criteria.fix_command_test = cd {workdir} && <same command>`
  (post-fix gate re-runs the same real tool, must exit 0 after agent edits)
- `promotion_eligible = true`

End-to-end smoke (2026-04-20): `generated_python_build_error_000` copied
`build_native.py` + `native_module.c` into a hermetic workdir, ran
`python3 build_native.py`, got a real `cc` compile error matching
`fatal error: Python\.h: No such file or directory`, and
`pre_failure_reproduced=True` was set with no agent running.
