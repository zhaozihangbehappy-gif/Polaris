# Polaris v4 Truth Table

Single source for current Polaris numbers and launch-state flags.

Codex sign-off: `scripts/pattern_validator_v4.py` is the sole authority for A/B/D and related release counts because it deterministically rescans the current `experience-packs-v4/` and `experience-packs-v4-candidates/` state. Launch-state rows such as `real_case_share` and `launch_verdict` come from the latest cited `eval/runs/<ts>/summary.json`, not from the validator. `FINAL_POLARIS_V4_AUDIT.md`, `AUTHORING_REPORT.md`, and `VERIFIED_PROMOTION_REPORT.md` are dated snapshots only.

## Validator Authority

- Authority script: `scripts/pattern_validator_v4.py`
- Fresh rerun at: `2026-04-21 12:17:03 +0800`
- Validator report: `validator-report-v4.json`
- `validator_run_hash` (`sha256` of `validator-report-v4.json`): `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a`
- Latest cited launch summary: `eval/runs/20260420T202045/summary.json`
- `launch_summary_hash` (`sha256` of latest cited summary): to be read from the file named above when needed for audit; the truth table lines below pin the exact file and line references.

## Definition Diff

| Source | What it counts | Why it differs |
|---|---|---|
| `scripts/pattern_validator_v4.py` | Current shard state only: A = official rows that pass clean `verified_live` audit now; B = official + candidate rows with sandbox-valid `authored_fixture` now; D = official + candidate rows that are schema-valid now. | Deterministic live recomputation; this is the authority. |
| `FINAL_POLARIS_V4_AUDIT.md` | A dated audit conclusion from the 2026-04-20 review pass, including snapshot statements such as `official_verified_count = 0`. | Narrative snapshot of one audit moment; can go stale as shard state changes. In the file itself, the `0` conclusion is tied to synthetic-recipe invalidation / no verified-live runner outcome, not to validator A-tier recomputation. |
| `AUTHORING_REPORT.md` | The authoring pipeline's on-disk sandbox-valid fixture stock at the time of that batch, e.g. `sandbox_valid_total_on_disk = 51`. | Counts authoring output inventory, not the full current validator B-tier over official + candidate pools. |
| `eval/runs/<ts>/summary.json` | Launch-state gates such as `launch_verdict`, `real_case_share`, and hard-gate pair pass rate for a specific run. | Operational launch readiness is not computed by the validator, so it must be read from a specific summary snapshot and kept separate from A/B/D count logic. |

## Truth Table

| Metric | Definition | Value | Live source | Anchor validator run hash |
|---|---|---:|---|---|
| `verified_live_count` (A) | Counts official-pool rows only. Required: `status=verified_live`; evidence survives per-evidence audit; `transcript_hash` is sha256 64-lower-hex; `artifact_path` exists; evidence is within the 90-day liveness window; pattern-level `authored_fixture` exists and is sandbox-valid; source is not `candidate_generated`. Not required: `real_case_share > 0`; real-issue-driven provenance; `launch_verdict=pass`; Gate-2 hard-gate pass (`CI flip` or `rounds >= 30% down`) on an eval pair. | 52 | `validator-report-v4.json:4-6,19,22,66` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `sandbox_ready_count` (B) | Counts official + candidate rows whose `authored_fixture` is sandbox-valid on the current shards. Required: `reviewer_record` says pre-fix failed, stderr matched, and post-fix passed. Not required: live-agent evidence; `verified_live`; real-issue provenance; launch hard-gate pass. | 105 | `validator-report-v4.json:9-11,20,25-26,57-58,65` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `schema_valid_count` (D) | Counts official + candidate rows that pass schema validation on the current shards. Required: shape-valid record only. Not required: authored fixture; sandbox pass; live-agent evidence; real-issue provenance; launch hard-gate pass. | 697 | `validator-report-v4.json:14-16,21,23,55` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `real_case_share` | Share of cases in the cited launch summary whose source is `real_issue`. Required for launch evaluation in that specific run summary. Not required for validator A/B/D count computation. | 0.0 | `eval/runs/20260420T202045/summary.json:21-29` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `launch_verdict.status` | Launch-status flag from the cited run summary, not from the validator. Internal research gate only — it governs when an evaluation snapshot is considered a full launch, NOT when Polaris can be published. Current run records `real_case_share 0% < 30%`, `hard-gate pair pass rate 0% < 50%`, `no real-agent pairs completed`. Not required for validator A/B/D counts. Not required for external release of the validator corpus. | fail | `eval/runs/20260420T202045/summary.json:21-29` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `hard_gate_pair_pass_rate` | Pair-level launch metric from the cited run summary: passing pairs / total pairs under the hard-gate rule in that summary snapshot. Not required for validator A/B/D counts. | 0.0 | `eval/runs/20260420T202045/summary.json:19-29` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `official_verified_count` | Official-pool verified count under the same validator pass; equal to A in the current script. Same gate semantics as A. | 52 | `validator-report-v4.json:22` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `official_schema_valid_count` | Schema-valid records in `experience-packs-v4/` only. | 167 | `validator-report-v4.json:23` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `candidate_schema_valid_count` | Schema-valid records in `experience-packs-v4-candidates/` only. | 530 | `validator-report-v4.json:55` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `official_authored_sandbox_valid_count` | Official-pool rows with sandbox-valid `authored_fixture` on the current shards. | 84 | `validator-report-v4.json:26` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `candidate_authored_sandbox_valid_count` | Candidate-pool rows with sandbox-valid `authored_fixture` on the current shards. | 21 | `validator-report-v4.json:58` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |
| `official_invalidated_evidence_total` | Invalidated official evidence rows retained for audit on the current shards. | 16 | `validator-report-v4.json:31` | `5a93969528a69414c040e0eeb4f7daf65ee369e9d5200f81aa1acafbb7389f9a` |

## Publication Contract

Any Polaris number or launch-state flag used externally must appear as a row in this file. If the number or flag is not present here, do not publish it.
