# Step 0: Real Execution Anchor

_Engineering plan — 2026-03-15_
_Author: Claude (audited by OpenClaw and Codex)_

---

## Goal

Prove that Polaris can orchestrate real work, validate it independently, fail on real errors, and recover — through a single new execution kind (`file_analysis`) that breaks the current tautological validation loop.

## Scope

This is the **minimum real execution anchor**, not a full adapter ecosystem.

One execution kind. One real task script. One independent validator. One real failure path. One real repair-then-retry.

## What "real" means here

- **Real adapter**: executes computation whose output is determined by filesystem state, not by contract fields.
- **Real validator**: re-reads the same source data independently, re-computes all metrics, and cross-checks. Catches adapter bugs, corruption, or lying.
- **Real failure**: comes from actual filesystem errors (FileNotFoundError), not `--simulate-error`.
- **Real repair**: the repair engine classifies a genuine error string, not a synthetic one.

## Deliverables

### New files

1. `scripts/polaris_file_analysis.py` — real file analysis task
   - Takes `--target` (path to a real file) and `--output-file`
   - Computes: line_count, word_count, char_count, sha256_bytes (raw bytes hash), first_line, last_line
   - Genuinely fails on missing/unreadable files
   - Writes structured JSON report

### Modified files

2. `scripts/polaris_validator.py` — add `independent_file_analysis` validator kind
   - Reads the adapter's output JSON
   - Independently reads the same target file
   - Re-computes line_count, word_count, char_count, sha256_bytes (from raw bytes)
   - Fails if any metric mismatches

3. `scripts/polaris_orchestrator.py`
   - Add `file_analysis` execution kind in `build_execution_contract`
   - Add `--analysis-target` CLI argument
   - Target defaults to a real Polaris script if not specified

4. `scripts/polaris_contract_planner.py` — add `file-analysis` capability

5. `scripts/polaris_runtime_demo.sh`
   - Add `file-analysis-local` adapter registration
   - Pass `POLARIS_ANALYSIS_TARGET` through to orchestrator

6. `scripts/polaris_regression.sh` — add three scenarios:
   - `real-analysis-success`: analyze a real file, independent validator passes
   - `real-analysis-failure-repair`: two-run scenario — target missing -> real failure -> blocks; create file; second run -> real success
   - Inline assertion: tamper with adapter output -> independent validator catches mismatch

## Acceptance criteria

1. `real-analysis-success` completes with `status == "completed"` and `execution_kind == "file_analysis"`
2. The validator kind is `independent_file_analysis`, not `json_status_file` or `runner_result_contract`
3. The validator independently re-reads the target file and re-computes sha256, line_count, word_count, char_count
4. `real-analysis-failure-repair` run 1 blocks with a real error (not `--simulate-error`)
5. The repair report classifies the real error as `path_or_missing_file`
6. `real-analysis-failure-repair` run 2 completes with independent validation after the file is created
7. Tampering with the adapter output (changing sha256) causes the independent validator to fail with a mismatch reason
8. All existing regression scenarios continue to pass unchanged

## Forbidden pseudo-completion states

1. **If the new adapter's output is still a copy of contract-injected fields, Step 0 is not complete.**
   The adapter must compute values (sha256, line_count, etc.) from real filesystem reads.

2. **If the validator checks only contract-echo fields, Step 0 is not complete.**
   The validator must independently re-read the same file and re-compute at least sha256 and line_count.

3. **If the failure scenario uses `--simulate-error`, Step 0 is not complete.**
   The failure must come from a real FileNotFoundError or equivalent.

4. **If the "independent" validator is a renamed copy of the same code path as the adapter, Step 0 is not complete.**
   The validator must be a separate code path that re-computes from source.

## Precise scope claims

Step 0 proves the following and no more:

1. **Real UTF-8 text file analysis anchor** — not general binary file analysis.
   The adapter reads raw bytes (`read_bytes()`), hashes them (`sha256_bytes`), and separately decodes as UTF-8 for text statistics.
   Non-UTF-8 files will fail at decode. This is acceptable for the anchoring purpose.

2. **Same-stack independent re-computation validator** — not heterogeneous validation.
   The validator is logically independent (separate code path, independent re-read, independent re-computation) but is still Python, same repo, same language. It is not a cross-language or cross-environment validator. This breaks the contract-echo tautology but does not prove cross-implementation consistency.

3. **Real failure + real classification + external-intervention retry** — not automatic repair.
   The failure is real (FileNotFoundError from filesystem). The classification is real (repair engine parses genuine stderr). The retry succeeds after external intervention (regression harness creates the missing file). The repair action tree remains probe-only; Polaris does not automatically fix the missing file.

## Non-goals

- Replacing all existing execution kinds with real ones
- Building a general-purpose adapter ecosystem
- Changing the repair action tree to perform real fixes (probe-only is fine)
- Platform-0 concerns (schema versioning, rollback, migration)
- Binary file analysis or non-UTF-8 support
- Heterogeneous cross-language validation

---

## Implementation sequence

1. Write `polaris_file_analysis.py`
2. Add `independent_file_analysis` to `polaris_validator.py`
3. Add `file_analysis` kind to orchestrator + contract planner
4. Update runtime demo script with adapter + target support
5. Add regression scenarios + assertions
6. Run full regression and verify zero breakage + all new assertions pass
