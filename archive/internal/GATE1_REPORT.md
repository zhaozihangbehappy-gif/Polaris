# Gate 1 Close-Out Report — Pattern Schema v4

**Date**: 2026-04-19
**Codex conditional approval carry-over**: main sentence allowed EN/platform rewrite at launch; 1000-tier is stretch goal, first-release tiers are 167/300/500; liveness gate enforced.

## Artifacts produced

| File | Purpose |
|---|---|
| `scripts/pattern_schema.py` | v4 dataclasses + `validate_shape()` + liveness check |
| `scripts/migrate_patterns_v4.py` | v3 → v4 migration, no fabrication |
| `scripts/pattern_validator_v4.py` | Shape + liveness gate |
| `scripts/sample_patterns_v4.py` | Random 10-sample audit |
| `experience-packs-v4/` | Migrated shards, schema_version=4 |
| `migration-report-v4.json` | Per-ecosystem migration counts |
| `validator-report-v4.json` | Schema + liveness counts |
| `migration-sample-v4.json` | Random 10 audit |

## Results

- **167/167 patterns** migrated schema-wise (100%)
- **501 human-review items** surfaced (3 per pattern: `false_paths`, `applicability_bounds`, `agent_reproducibility`)
- **0/167 count toward the 1000 target** — correct and intentional. Liveness gate requires `verified_live` evidence on ≥1 agent within 90 days; Gate 2 populates this.
- **Random 10-sample**: all 10 confirm `false_paths=[]` and `agent_reproducibility.evidence=[]`. No fabricated fields.

## What this unlocks

- Gate 2 (Eval Harness) can start: the liveness field is now a first-class schema property that runners will write into.
- The 1000-target is now a **computed** number, not a declaration. Validator reports it on every run.
- User's constraint enforced at code level: *"这1000个我不要各大agent里面实现不了或者说根本不存在此问题或者无效的"* — patterns that no longer reproduce on current agents will mechanically fail the liveness gate and not count.

## What Gate 1 does NOT do

- Does not author `false_paths`. That is domain expert + Codex authoring work; pending.
- Does not test any pattern against real Cursor/Claude Code/Codex. That is Gate 2.
- Does not delete or re-tier the v3 data. `legacy_v3` is preserved in every v4 record for rollback.
