# Invalidated Evidence Report

Generated: 2026-04-19
Trigger: Codex reviewer rejection of the `official_verified_count=2` claim from
run `eval/runs/20260419T171919/` (published in the previous
`VERIFIED_PROMOTION_REPORT.md`).

## Root cause

The orchestrator used a **persistent per-case workdir** (`/tmp/_polaris_caseXX`)
that it did NOT reset between variants. Ordering was:

1. `baseline` runs — agent modifies `/tmp/_polaris_case001/`, applies fix.
2. `polaris` runs — same directory is reused, already in the fixed state.
3. Agent inspects the workdir, observes no failure, reports
   "already fixed / no edits needed / bad state is not reproduced", exits
   `ci_pass=True`.
4. Evidence writer sees `ci_pass + rounds != None + transcript nonempty`,
   appends `verified_live` AgentReproEvidence.

The rows satisfied the schema-level audit (sha256 hash, artifact exists,
status string valid, date within 90 days) but did **not** prove the pattern is
reproducible today. They only proved that a stale, already-fixed directory
existed when the run started.

## Contamination signals present in the transcripts

Grepping `eval/runs/20260419T171919/transcripts/`:

| phrase (case-insensitive) | hits |
|---|---|
| `already fixed` / `already passes` | present in claude_code polaris runs of case_001 and case_002 |
| `no edits needed` | present in claude_code baseline runs |
| `failure does not reproduce` / `bad state is not reproduced` | present in codex polaris run of case_002 |

Any one of these phrases means the hermetic precondition failed — the agent
did not face the failure the pattern claims to diagnose. Evidence cannot be
harvested from such a run.

## Evidence rows invalidated

Moved from `agent_reproducibility.evidence[]` into a new
`agent_reproducibility.invalidated_evidence[]` array. Status flipped from
`verified_live` to `invalidated_contaminated_fixture`. Original
`transcript_hash`, `artifact_path`, `date_verified`, `agent`, `agent_version`,
`notes` preserved for audit. New fields added: `invalidation_reason`,
`invalidated_at=2026-04-19T18:30:00+00:00`.

| pattern_id | agent | variant | transcript_hash (prefix) |
|---|---|---|---|
| python.missing_dependency.000 | codex | baseline | `c58b87b054…` |
| python.missing_dependency.000 | codex | polaris | `3b17e0274d…` |
| python.missing_dependency.000 | claude_code | baseline | `86ad49471e…` |
| python.missing_dependency.000 | claude_code | polaris | `ba8ad83d66…` |
| node.missing_dependency.000 | codex | baseline | `f7d37c0bd7…` |
| node.missing_dependency.000 | codex | polaris | `8c3a345fd4…` |
| node.missing_dependency.000 | claude_code | baseline | `122e516bdf…` |
| node.missing_dependency.000 | claude_code | polaris | `e99adaefb6…` |

Total: **8 rows, 2 pattern_ids.** `scripts/invalidate_contaminated_evidence.py`
is the one-shot migration that performed the move.

## Current counts

From `validator-report-v4.json` after invalidation:

| Metric | Value |
|---|---|
| official_verified_count | **0** (was 2, now honestly 0) |
| official_schema_valid_count | 167 |
| official_invalidated_evidence_total | 8 |
| candidate_schema_valid_count | 530 |
| candidate_live_present | [] |

## What counts as `verified_live` going forward

The `AgentReproEvidence.audit_errors()` gate now requires **all** of:

1. `status == "verified_live"`
2. `agent ∈ {cursor, claude_code, codex}`
3. `date_verified` ISO-8601 within 90 days
4. `artifact_path` exists on disk at validator runtime
5. `transcript_hash` is 64 lowercase hex sha256
6. `pre_failure_reproduced == true` (new) — orchestrator ran
   `expected_failure_command` in the hermetic workdir **before** the agent saw
   it, and the stderr matched `expected_failure_stderr_regex`
7. Source is not `candidate_generated`

Evidence writer will additionally scan the transcript for contamination
phrases; any hit → the row is written with
`status=blocked_contaminated_run` and does not count.

## Why we kept the invalidated rows instead of deleting

Deletion would erase the Codex reviewer's audit trail of why the earlier claim
was wrong. Next time someone looks at these two patterns, the
`invalidated_evidence[]` array shows that a previous run was attempted, which
runner+variant produced each contaminated transcript, and the exact reason it
was thrown out. That protects against silently re-asserting the same bad
evidence.

## Rebuild commitment

- `eval/orchestrator.py` → hermetic per-variant workdirs under
  `/tmp/_polaris_runs/<run_id>/<runner>/<case_id>/<variant>/`, rebuilt from a
  fixture manifest, with `expected_failure_command` executed before the agent.
- Runners → accept an injected workdir, write pre-failure and post-fix command
  outputs into the transcript.
- `eval/evidence_writer.py` → block any run whose transcript contains a
  contamination phrase or whose `pre_failure_reproduced` flag is false.
- `eval/case_generator.py` → emit 697 case skeletons so the 167 official +
  530 candidate pool can be driven through the hermetic harness.

Progress on those rebuilds tracked in `HANDOFF.md` and in the follow-up
`VERIFIED_PROMOTION_REPORT.md`.
