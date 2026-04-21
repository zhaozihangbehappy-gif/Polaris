"""Validate v4 pattern shards — official pack AND candidate pool.

Counts reported:
  tier_a_verified_live_count       — official records with clean evidence audit,
                                     transcript_hash matches sha256 hex,
                                     artifact_path exists on disk,
                                     status=verified_live within 90 days,
                                     source != candidate_generated
  tier_b_sandbox_ready_count       — official + candidate records with a
                                     sandbox-valid authored_fixture
  tier_d_schema_valid_count        — official + candidate records passing
                                     schema validation
  official_schema_valid_count      — official records passing shape check
  official_schema_invalid_count    — shape failures in official pack
  candidate_schema_valid_count     — candidate records passing shape check
  candidate_schema_invalid_count   — shape failures in candidate pool
  candidate_live_present           — LIST of candidate pattern_ids that carry
                                     any evidence (policy violation)
  invalid_evidence_examples        — offending pattern_id → reason list

candidate_generated patterns remain in the candidate pool until promoted by
verified live evidence; any evidence on an unpromoted candidate is flagged.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pattern_schema import (
    AgentReproEvidence,
    AgentReproducibility,
    pattern_level_audit_errors,
    validate_shape,
)

REPO = Path(__file__).resolve().parent.parent
OFFICIAL = REPO / "experience-packs-v4"
CANDIDATE = REPO / "experience-packs-v4-candidates"

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LIVENESS_DAYS = 90
CANDIDATE_SOURCE_TAG = "candidate_generated"

CANDIDATE_SANDBOX_READY_NOTE = (
    "Codex-authored subset, higher quality than the raw candidate pool but not "
    "verified_live. Candidate records remain separate until evidence_writer "
    "promotes a verified live run into experience-packs-v4/."
)


def _audit_record_liveness(rec: dict) -> tuple[bool, list[str]]:
    """Return (counts, reasons). reasons is empty iff counts=True cleanly."""
    reasons: list[str] = []
    pid = rec.get("pattern_id", "?")
    if rec.get("source") == CANDIDATE_SOURCE_TAG:
        reasons.append("source=candidate_generated never verifies")
        return False, reasons
    # Pattern-level contamination check: synthetic recipes cannot promote.
    for err in pattern_level_audit_errors(rec):
        reasons.append(f"pattern-level: {err}")
    raw_ar = rec.get("agent_reproducibility") or {}
    raw_ev = raw_ar.get("evidence") or []
    clean: list[AgentReproEvidence] = []
    for i, raw in enumerate(raw_ev):
        try:
            ev = AgentReproEvidence(**raw)
        except TypeError as exc:
            reasons.append(f"evidence[{i}] shape: {exc}")
            continue
        errs = ev.audit_errors()
        if errs:
            reasons.extend(f"evidence[{i}]: {e}" for e in errs)
            continue
        if not SHA256_RE.fullmatch(ev.transcript_hash):
            reasons.append(f"evidence[{i}]: transcript_hash not 64-hex sha256")
            continue
        artifact_path = (REPO / ev.artifact_path) if not Path(ev.artifact_path).is_absolute() else Path(ev.artifact_path)
        if not artifact_path.exists():
            reasons.append(f"evidence[{i}]: artifact_path does not exist: {ev.artifact_path}")
            continue
        clean.append(ev)
    # Any pattern-level error blocks promotion regardless of clean evidence.
    if reasons:
        return False, reasons
    counts = AgentReproducibility(evidence=clean).counts_toward_1000(max_age_days=LIVENESS_DAYS)
    return counts, reasons


def _count_pool(root: Path) -> dict:
    from pattern_schema import _is_synthetic_recipe
    schema_valid = 0
    schema_invalid = 0
    verified = 0
    invalidated_total = 0
    authored_fixture_candidate = 0
    authored_sandbox_valid = 0
    synthetic_pre = 0
    synthetic_fix = 0
    invalidated_by_pattern: list[tuple[str, int]] = []
    shape_errors: list[tuple[str, list[str]]] = []
    evidence_errors: list[tuple[str, list[str]]] = []
    for shard_path in sorted(root.rglob("*.json")):
        shard = json.loads(shard_path.read_text())
        for rec in shard.get("records", []):
            errs = validate_shape(rec)
            if errs:
                schema_invalid += 1
                if len(shape_errors) < 10:
                    shape_errors.append((rec.get("pattern_id", "?"), errs))
                continue
            schema_valid += 1
            sv_cmd = (rec.get("shortest_verification") or {}).get("command") or ""
            fx_cmd = (rec.get("fix_path") or {}).get("fix_command") or ""
            if _is_synthetic_recipe(sv_cmd):
                synthetic_pre += 1
            if _is_synthetic_recipe(fx_cmd):
                synthetic_fix += 1
            af = rec.get("authored_fixture")
            if af:
                authored_fixture_candidate += 1
                rr = af.get("reviewer_record") or {}
                if (
                    rr.get("sandbox_pre_fix_exit_code") not in (None, 0)
                    and rr.get("sandbox_pre_fix_stderr_match")
                    and rr.get("sandbox_post_fix_exit_code") == 0
                ):
                    authored_sandbox_valid += 1
            counts, reasons = _audit_record_liveness(rec)
            if counts:
                verified += 1
            elif reasons and len(evidence_errors) < 20 and rec.get("agent_reproducibility", {}).get("evidence"):
                evidence_errors.append((rec.get("pattern_id", "?"), reasons))
            inv = rec.get("agent_reproducibility", {}).get("invalidated_evidence", []) or []
            if inv:
                invalidated_total += len(inv)
                invalidated_by_pattern.append((rec.get("pattern_id", "?"), len(inv)))
    return {
        "schema_valid": schema_valid,
        "schema_invalid": schema_invalid,
        "verified": verified,
        "invalidated_evidence_total": invalidated_total,
        "invalidated_evidence_by_pattern": invalidated_by_pattern,
        "authored_fixture_candidate_count": authored_fixture_candidate,
        "authored_sandbox_valid_count": authored_sandbox_valid,
        "synthetic_pre_failure_recipe_count": synthetic_pre,
        "synthetic_fix_recipe_count": synthetic_fix,
        "shape_errors_sample": shape_errors,
        "evidence_errors_sample": evidence_errors,
    }


def scan_official() -> dict:
    return _count_pool(OFFICIAL)


def scan_candidate() -> dict:
    out = _count_pool(CANDIDATE)
    live_present: list[str] = []
    wrong_source_with_evidence: list[str] = []
    for shard_path in sorted(CANDIDATE.rglob("*.json")):
        shard = json.loads(shard_path.read_text())
        for rec in shard.get("records", []):
            if rec.get("agent_reproducibility", {}).get("evidence"):
                live_present.append(rec.get("pattern_id", "?"))
                if rec.get("source") != CANDIDATE_SOURCE_TAG:
                    wrong_source_with_evidence.append(rec.get("pattern_id", "?"))
    out["live_present"] = live_present
    out["wrong_source_with_evidence"] = wrong_source_with_evidence
    return out


def main() -> int:
    official = scan_official()
    candidate = scan_candidate()
    tier_a_verified_live_count = official["verified"]
    tier_b_sandbox_ready_count = (
        official["authored_sandbox_valid_count"]
        + candidate["authored_sandbox_valid_count"]
    )
    tier_d_schema_valid_count = official["schema_valid"] + candidate["schema_valid"]
    report = {
        "quality_tiers": {
            "A": {
                "metric": "verified_live_count",
                "count": tier_a_verified_live_count,
                "scope": "official pool only; clean verified_live evidence within liveness window",
            },
            "B": {
                "metric": "sandbox_ready_count",
                "count": tier_b_sandbox_ready_count,
                "scope": "official + candidate records with sandbox-valid authored_fixture",
            },
            "D": {
                "metric": "schema_valid_count",
                "count": tier_d_schema_valid_count,
                "scope": "official + candidate records passing schema validation",
            },
        },
        "tier_a_verified_live_count": tier_a_verified_live_count,
        "tier_b_sandbox_ready_count": tier_b_sandbox_ready_count,
        "tier_d_schema_valid_count": tier_d_schema_valid_count,
        "official_verified_count": official["verified"],
        "official_schema_valid_count": official["schema_valid"],
        "official_schema_invalid_count": official["schema_invalid"],
        "official_authored_fixture_candidate_count": official["authored_fixture_candidate_count"],
        "official_authored_sandbox_valid_count": official["authored_sandbox_valid_count"],
        "official_synthetic_pre_failure_recipe_count": official["synthetic_pre_failure_recipe_count"],
        "official_synthetic_fix_recipe_count": official["synthetic_fix_recipe_count"],
        "official_shape_errors_sample": official["shape_errors_sample"],
        "invalid_evidence_examples": official["evidence_errors_sample"],
        "official_invalidated_evidence_total": official["invalidated_evidence_total"],
        "official_invalidated_evidence_by_pattern": official["invalidated_evidence_by_pattern"],
        "candidate_verified_count": candidate["verified"],
        "candidate_schema_valid_count": candidate["schema_valid"],
        "candidate_schema_invalid_count": candidate["schema_invalid"],
        "candidate_authored_fixture_candidate_count": candidate["authored_fixture_candidate_count"],
        "candidate_authored_sandbox_valid_count": candidate["authored_sandbox_valid_count"],
        "candidate_synthetic_pre_failure_recipe_count": candidate["synthetic_pre_failure_recipe_count"],
        "candidate_synthetic_fix_recipe_count": candidate["synthetic_fix_recipe_count"],
        "candidate_shape_errors_sample": candidate["shape_errors_sample"],
        "candidate_live_present": candidate["live_present"],
        "candidate_wrong_source_with_evidence": candidate["wrong_source_with_evidence"],
        "candidate_sandbox_ready_note": CANDIDATE_SANDBOX_READY_NOTE,
        "total_authored_sandbox_valid": tier_b_sandbox_ready_count,
        "verified_live_gate": f"verified_live on >=1 agent within {LIVENESS_DAYS} days, clean audit, artifact exists, pattern carries sandbox-valid authored_fixture",
        "release_positioning": "Small, auditable benchmark: every B-tier fixture can be rerun hermetically; A-tier is live-agent verified.",
    }
    (REPO / "validator-report-v4.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
