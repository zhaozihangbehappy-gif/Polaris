# Gate 2 v0 Close-Out Report — Eval Harness Plumbing

**Date**: 2026-04-19
**Scope**: v0 means plumbing proven end-to-end; real agent integration deferred to v1.

## Artifacts

| File | Purpose |
|---|---|
| `scripts/pattern_schema.py` | Evidence hardened: agent/status enum, ISO date, `artifact_path` + `transcript_hash` required for `verified_live` |
| `scripts/pattern_validator_v4.py` | Audits evidence shape and reports errors alongside liveness count |
| `eval/metrics.py` | Codex's 5 metrics + `MetricDelta` with NARRATIVE.md §4 hard-gate logic |
| `eval/runners/base.py` | Unified `Runner` contract (木桶 equal) |
| `eval/runners/codex_runner.py` | Stub — documents real CLI invocation |
| `eval/runners/claude_code_runner.py` | Stub — documents real CLI invocation |
| `eval/runners/cursor_runner.py` | Stub — transcript-ingest shape |
| `eval/runners/mock_runner.py` | Deterministic synthetic metrics. **Not for external claims.** |
| `eval/cases/case_001..003.json` | 3 seed cases (pattern-reverse) covering Python/Node/Docker |
| `eval/orchestrator.py` | Runs case × runner × {baseline, with_polaris} matrix |
| `eval/runs/{ts}/` | Timestamped results + summary |

## Proofs

1. **Evidence audit works.** Good evidence (agent, enum status, ISO date, `artifact_path`, 32-char `transcript_hash`) validates; missing artifact or bad enum raises structured errors.
2. **Schema revalidation clean.** 167/167 still schema_valid after hardening; 0/167 count toward 1000 (as expected — no real evidence yet).
3. **Orchestrator matrix works.** `--runner mock,codex,claude_code,cursor` → 24 runs attempted, 6 completed (mock), 3 stubs cleanly recorded `NotImplementedError`. No crashes, no fabricated stub metrics.
4. **Hard-gate actually bites.** MockRunner dry-run: of 3 case pairs, 2/3 passed the hard gate (CI-pass flip OR rounds ≥30% down). Case 001 failed because rounds only improved 16.7% and no CI flip — this is the anti-self-hype保险丝 working correctly.

## What v0 does NOT do

- Does not invoke real Cursor / Claude Code / Codex. Three runners are stubs with documented CLI shapes. Running them requires your subscribed machine.
- Does not author `false_paths` on migrated patterns. Still 501 `NEEDS_HUMAN_REVIEW` items outstanding from Gate 1.
- Does not have real case repos. Cases point at `/tmp/_polaris_caseXX` paths that need fixture snapshots before live runners can use them.
- Does not include real-issue-sourced cases (the 30% share). Pending GitHub issue curation.

## Gate 2 v1 (next increment)

Not to be started without explicit go-signal:

1. Implement `CodexRunner.run()` — subprocess `codex exec`, parse session log
2. Implement `ClaudeCodeRunner.run()` — `claude -p --output-format stream-json`
3. Implement `CursorRunner.run()` — transcript-file ingest
4. Build fixture snapshots for case 001-003 under `eval/fixtures/`
5. Curate 1-2 real GitHub issue cases (30% share target)
6. First real 3-runner × 3-case matrix run; evidence populated into v4 patterns via a separate `eval/evidence_writer.py`
7. Validator re-run: expect `counts_toward_1000` to go from 0 to N>0

## Signatures

- Codex's non-blocking evidence hardening: **absorbed into v0**, not deferred
- User's 木桶/equal-priority instruction: **respected**, all three stubs sit at same level of readiness, no P0/P1/P2 tiering in the code
- NARRATIVE.md §4 anti-self-hype gate: **enforced in `metrics.py:passes_hard_gate`**

## 2026-04-19 amendments (Codex's three constraints)

1. **`transcript_hash` tightened to sha256-64-hex.** `pattern_schema.py:audit_errors` now rejects anything but 64 lowercase hex. Verified: 64ok, 32fail, uppercase fail.
2. **`launch_verdict` added to orchestrator summary.** Statuses: `pass`, `fail`, `blocked_mock_only`. Gates on pair-pass rate ≥50% AND real_issue case share (≥30% v0, ≥50% launch). Mock-only runs auto-block. Verified: mock-only → blocked_mock_only; mock+stub → fail (0% real cases).
3. **Fixture manifests built + validator.** `eval/fixtures/{case_id}/manifest.json` records per-file sha256, dependency versions, build commands, expected-failure command + stderr regex. `fixtures_manifest.py validate` rehashes and confirms match. All 3 cases validate clean.

## Added artifacts

| File | Purpose |
|---|---|
| `eval/fixtures/case_001..003/files/` | Source payloads for each case |
| `eval/fixtures/case_001..003/manifest.json` | sha256-audited manifest |
| `eval/fixtures_manifest.py` | Build + validate manifests |
| `V1_INTEGRATION_CHECKLIST.md` | Step-by-step for subscribed machine |
