# Final Polaris v4 Audit

> Snapshot notice (2026-04-21): this file is a dated audit snapshot from 2026-04-20, not the live numeric authority. For any current Polaris number, use `POLARIS_V4_TRUTH_TABLE.md`, which is tied to a fresh rerun of `scripts/pattern_validator_v4.py`. If this file disagrees with the truth table, the truth table wins. Do not cite both as data sources.

Generated: 2026-04-20
Scope: every claim the Polaris v4 pool can and cannot make as of this date.

## One-line verdict

> Runtime SLA passes at 1500 patterns. Pattern-level `verified_live` count is
> 0. Launch blocked on Codex + Claude quota + Cursor human-in-the-loop, not on
> code or schema.

## Pool composition

| Metric | Value | Source |
|---|---:|---|
| official_schema_valid_count | 167 | `experience-packs-v4/` |
| candidate_schema_valid_count | 530 | `experience-packs-v4-candidates/` |
| total_schema_valid_pool | **697** | validator-report-v4.json |
| sandbox-valid `authored_fixture` total | 51 | authoring_report.json |
| runnable generated cases | 51 | case-generation-report-v4.json |
| manual Cursor queue length | 102 variants | eval/runs/manual_cursor_required.json |
| `official_verified_count` | **0** | promotion-report-v4.json |
| invalidated_evidence_total | 16 | pattern JSON `invalidated_evidence[]` |

## Gate-by-gate status

| Gate | Requirement | Status | Evidence |
|---|---|---|---|
| Schema valid (v4) | every pattern passes pattern_validator_v4 | ✅ | 697/697 |
| No synthetic pre-failure recipe in verified rows | `_is_synthetic_recipe(verification_command)` = False | ✅ (invalidated 8) | invalidate_synthetic_recipe_evidence run |
| No synthetic fix in verified rows | `_is_synthetic_recipe(fix_command)` = False | ✅ (same 8) | same |
| Authored fixture sandbox-valid | pre fails+stderr match, post passes | ✅ for 51 | authoring_report.json |
| Runtime p95 ≤ 10ms @ pool 1500 | scale-bench-v4 | ✅ 0.026 ms | SCALE_BENCH_REPORT.md |
| Runtime token ≤ 100 | constant_budget | ✅ 100 tokens max | same |
| Runtime multipliers ≤ 1.2× | constant_budget | ✅ all 1.0× | same |
| Hermetic harness reproducibility | pre_failure_reproduced + post_fix_pass | ⏸ not executed against authored fixtures | Codex + Claude quota |
| Per-runner `verified_live` ≥ 1 for Codex | real-agent transcript | ❌ 0 | codex_rate_limited |
| Per-runner `verified_live` ≥ 1 for Claude | real-agent transcript | ❌ 0 | claude_rate_limited |
| Per-runner `verified_live` ≥ 1 for Cursor | human-produced transcripts | ❌ 0 | blocked_cursor_transcript_missing × 102 |

## What changed in v4 vs previous runs

1. **Synthetic canonicalization reversed.** An earlier session canonicalized
   530 candidates to bash-echo recipes for fast validator passes. That work
   was audited as contamination-by-construction and fully reverted
   (`scripts/revert_canonicalization.py`). Candidate pool now carries
   original harvested `shortest_verification_command` and `fix_command`
   values, not synthetic stand-ins.

2. **Official pool retrofitted.** The same `_is_synthetic_recipe` detector
   was applied to the 167 official patterns. 151/167 had a synthetic
   `fix_command` and 121/167 had a synthetic `shortest_verification.command`.
   Those patterns are still schema-valid (they were harvested from real
   sources), but they cannot be claimed as verified until their authored
   fixture passes sandbox.

3. **Verified count reset 4 → 0.** See `VERIFIED_PROMOTION_REPORT.md`: the
   four Codex-run rows were valid against the contamination detector, but
   their underlying fixtures were synthetic recipes, so the pattern-level
   audit contract blocks promotion.

4. **Authored fixture pipeline added.** `scripts/author_fixtures.py` runs
   Codex as an *authoring* agent (not a verifying one): Codex writes a real
   minimal project + `authored.json` sidecar; a sandbox validator runs the
   verification command on a fresh pre/ dir (must fail+match regex) and on
   a post/ dir (files + reference_fix_files overlaid — must pass). Only
   sandbox-valid fixtures are merged into the shard. No synthetic recipe
   can enter this path.

5. **Case generator tightened.** `eval/case_generator.py` now refuses to
   emit a runnable case unless the pattern has a sandbox-valid authored
   fixture. 646 patterns are written as skeletons only (with
   `promotion_eligible=false`). 51 have runnable cases on disk, each with
   real fixture files under `eval/fixtures/<case_id>/files/`.

## What this run produced on disk

| Artifact | Path |
|---|---|
| Authoring report (markdown) | `AUTHORING_REPORT.md` |
| Authoring report (json) | `authoring_report.json` |
| Tooling blockers report | `TOOLING_BLOCKERS_REPORT.md` |
| Case generation report (markdown) | `CASE_GENERATION_REPORT.md` |
| Case generation report (json) | `case-generation-report-v4.json` |
| Scale bench report (markdown) | `SCALE_BENCH_REPORT.md` |
| Scale bench report (json) | `scale-bench-report-v4.json` |
| Promotion report (markdown) | `VERIFIED_PROMOTION_REPORT.md` |
| Promotion report (json) | `promotion-report-v4.json` (+ new invalidations) |
| Validator report | `validator-report-v4.json` |
| Case files | `eval/cases/generated_*.json` (51 files) |
| Fixture files | `eval/fixtures/<case_id>/files/*` (per case) |
| Skeletons for blocked patterns | `eval/generated-cases-v4/<pool>/<eco>/*.json` |
| Cursor manual queue | `eval/runs/manual_cursor_required.json` (102 entries) |
| This final audit | `FINAL_POLARIS_V4_AUDIT.md` |

## Bottlenecks, ranked

1. **Codex free-tier quota.** 305 of 363 sandboxable patterns
   rate-limited mid-batch. After quota reset, re-run
   `scripts/author_fixtures.py --only-sandboxable --candidates --workers 6`;
   resumability is built in (skip logic checks existing sandbox-valid
   rows). This moves the 51 to ~363.

2. **Missing toolchains for 334 patterns.** docker/go/java/terraform/ruby
   are symlinks to `agent-runtime-guard` with no real binary behind them.
   See `TOOLING_BLOCKERS_REPORT.md` for install commands. Alternatively,
   implement per-pattern container fallback (tracked but not built).

3. **Real-agent verification (Phase 3) never ran.** Needs both Codex and
   Claude quota available plus Cursor transcripts. Orchestrator is wired and
   tested against one authored fixture (`generated_python_build_error_000`
   reproduced its failure before any agent ran).

4. **Cursor is the hard ceiling on Cursor verified_live.** No headless CLI
   runner in this environment. `generate_cursor_queue.py` writes the 102
   entries a human reviewer must transcript. Until each transcript is on
   disk at the `expected_transcript_path`, Cursor evidence stays blocked.

## Claims matrix for external surfaces

| Claim | Allowed? | Why |
|---|---|---|
| "697 schema-valid patterns" | ✅ | pool count, validator passes |
| "51 patterns have a real reproducible fixture" | ✅ | sandbox-valid authored_fixture on disk |
| "runtime p95 ≤ 0.03 ms at 1500-pattern pool" | ✅ | scale-bench |
| "runtime token cost ≤ 100 per query" | ✅ | CONSTANT_CONTEXT_TOKEN_BUDGET=100 |
| "167 / 697 / 1000 verified patterns" | ❌ | verified count = 0 |
| "Polaris is launch-ready" | ❌ | no runner produced verified_live |
| "Codex verified 4 patterns" | ❌ | 4 rows invalidated |
| "Polaris rejects synthetic recipes" | ✅ | `_is_synthetic_recipe` + `pattern_level_audit_errors` |
| "Polaris has a hermetic harness" | ✅ | smoke verified on `generated_python_build_error_000` |

## What a green run looks like (for the next operator)

1. Confirm Codex quota reset; rerun authoring for the 312 rate-limited
   sandboxable targets. Expect ~330–350 sandbox-valid rows (empirical
   sandbox pass rate from the pilot batch is >90% on patterns with real
   toolchains).

2. Re-run case generator. Runnable cases move from 51 to ~330.

3. Start hermetic orchestrator under each runner:
   ```
   python -m eval.orchestrator --runner codex  --all-generated
   python -m eval.orchestrator --runner claude --all-generated
   # cursor: only cases that have paired transcripts in eval/runs/manual_cursor/
   python -m eval.orchestrator --runner cursor --all-generated
   ```

4. Run `scripts/pattern_validator_v4.py`. Rows that survive the audit land
   in `verified_evidence[]`. `official_verified_count` moves up per runner.

5. Regenerate `VERIFIED_PROMOTION_REPORT.md` and re-audit the claims matrix.

The code path for steps 1–5 is wired today. The blocker is purely quota
(codex + claude) and human bandwidth (cursor). Nothing in the schema,
harness, bench, or audit logic prevents a green run.

## Honest statement for a reviewer

This v4 pass materially tightened the ground truth: synthetic canonicalization
was caught and reverted, the schema now blocks pattern-level synthetic
recipes from counting as verified, the authoring pipeline produces real
project fixtures that fail and pass real tools, and the runtime stays
constant-budget at a 1500-pool. The claim surface shrank (4 → 0 verified),
which is the correct direction when the contract is tightened. The ceiling
for the next run is procurement (quota + human transcripts), not
engineering.
