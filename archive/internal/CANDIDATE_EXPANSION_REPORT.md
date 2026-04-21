# Candidate Expansion Report (v4)

Generated: 2026-04-20

## Counts

| Pool | Schema-valid | Sandbox-ready | Verified-live |
|---|---:|---:|---:|
| `experience-packs-v4/` official | 167 | 84 | 52 |
| `experience-packs-v4-candidates/` candidate | 530 | 21 | 0 |
| total | 697 | 105 | 52 |

The 530 candidate records remain in the repository. They are part of D-tier schema-valid inventory. The 21 candidate records with sandbox-valid authored fixtures are counted in B-tier, with an explicit note that they are not verified_live.

## Per-ecosystem Distribution (Candidates)

| Ecosystem | Count |
|---|---:|
| python | 120 |
| node | 120 |
| docker | 100 |
| go | 60 |
| rust | 50 |
| java | 50 |
| ruby | 15 |
| terraform | 15 |
| **total** | **530** |

See `candidate-report-v4.json` for the per-error-class breakdown and integrity checks.

## Integrity Checks

From `candidate-report-v4.json`:

- `schema_valid_count`: 530
- `rejected_count`: 0
- `duplicate_fingerprints_count`: 0
- `policy_violations.leaked_evidence_ids`: []
- `policy_violations.wrong_source_ids`: []
- `policy_violations.missing_human_review_flag_ids`: []

Sampling confirmed no candidate record contains forged evidence, no record has a source other than `candidate_generated`, and every record flags the required human-review fields.

## Promotion Path

The candidate-to-official path remains available for selective high-value records:

1. Derive a runnable case from the candidate.
2. Run a real agent through the hermetic harness.
3. Let `eval/evidence_writer.py` append clean `verified_live` evidence.
4. Promote the record into `experience-packs-v4/`.
5. Re-run `scripts/pattern_validator_v4.py`.

This path is not the primary roadmap now. The release story is A/B/D transparency: live-verified, sandbox-ready, schema-valid.

## Not Promised

- Raw candidate count is not verified-live evidence.
- B-tier sandbox-ready records are not live-agent verified.
- The project is not pursuing a bulk target count as its core release claim.
