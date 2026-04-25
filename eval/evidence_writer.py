# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Evidence writer — promote verified runs into v4 pattern evidence.

Input:
  eval/runs/<ts>/results.json
Output:
  (1) Per-evidence transcript file:
        eval/runs/<ts>/transcripts/<runner>__<case_id>__<variant>.txt
      artifact_path written into AgentReproEvidence points here.
  (2) Updated shards in experience-packs-v4/<eco>/<class>.json
      - existing records: append evidence (dedup by agent+transcript_hash)
      - candidates promoted from experience-packs-v4-candidates/: record moved
        with source='verified_candidate_promoted' + evidence appended; removed
        from candidate shard in the same commit so it never double-counts.
  (3) promotion-report-v4.json at repo root.

Write gate (per user directive):
  - runner_name ∈ {codex, claude_code, cursor}   — mock always ignored
  - metrics.ci_pass is True
  - metrics.rounds_to_root_cause is not None
  - transcript is a non-empty string
  - resolved pattern_id is known (via case.reverse_from_pattern)
  - transcript_hash is 64 lowercase hex
  - artifact_path exists after write

Duplication:
  (pattern_id, agent, transcript_hash) seen before → skipped.

Nothing is written for runs that miss any of the above. There is no silent
fallback and no backfill from mock runs — if a run cannot be turned into real
evidence, it is reported as blocked with a reason.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from eval.hermetic import scan_contamination

REPO = Path(__file__).resolve().parent.parent
OFFICIAL = REPO / "experience-packs-v4"
CANDIDATE = REPO / "experience-packs-v4-candidates"
CASES_DIR = REPO / "eval" / "cases"

REAL_AGENTS = {"codex", "claude_code", "cursor"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _load_case_map() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(CASES_DIR.glob("*.json")):
        if p.name.startswith("_"):
            continue
        try:
            d = json.loads(p.read_text())
        except json.JSONDecodeError:
            continue
        out[d["case_id"]] = d
    return out


def _find_shard(root: Path, pattern_id: str) -> Optional[Path]:
    for shard_path in root.rglob("*.json"):
        try:
            shard = json.loads(shard_path.read_text())
        except json.JSONDecodeError:
            continue
        for rec in shard.get("records", []):
            if rec.get("pattern_id") == pattern_id:
                return shard_path
    return None


def _locate_pattern(pattern_id: str) -> tuple[Optional[Path], str]:
    """Return (shard_path, pool_tag) where pool_tag ∈ {official,candidate}."""
    p = _find_shard(OFFICIAL, pattern_id)
    if p is not None:
        return p, "official"
    p = _find_shard(CANDIDATE, pattern_id)
    if p is not None:
        return p, "candidate"
    return None, "unknown"


def _write_transcript(runs_dir: Path, runner_name: str, case_id: str,
                      polaris_enabled: bool, transcript: str) -> Path:
    out_dir = runs_dir / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)
    variant = "polaris" if polaris_enabled else "baseline"
    path = out_dir / f"{runner_name}__{case_id}__{variant}.txt"
    path.write_text(transcript)
    return path


def _evidence_from_result(result: dict, case_map: dict[str, dict],
                          runs_dir: Path) -> tuple[Optional[dict], Optional[str], str]:
    """Return (evidence_dict, pattern_id, reason). evidence=None iff blocked."""
    runner = result.get("runner_name", "")
    if runner not in REAL_AGENTS:
        return None, None, f"ignored: runner={runner} is not a real agent"
    if result.get("status", "completed") != "completed":
        return None, None, f"blocked: status={result.get('status')}"
    if result.get("blocked_reason"):
        return None, None, f"blocked: {result.get('blocked_reason')}"
    if result.get("pre_failure_reproduced") is not True:
        return None, None, "blocked: pre_failure_reproduced is not True"
    workdir_manifest_hash = result.get("workdir_manifest_hash") or ""
    if not SHA256_RE.fullmatch(workdir_manifest_hash):
        return None, None, "blocked: missing or invalid workdir_manifest_hash"
    metrics = result.get("metrics") or {}
    if metrics.get("ci_pass") is not True:
        return None, None, "blocked: ci_pass is not True"
    if metrics.get("rounds_to_root_cause") in (None, 0):
        return None, None, "blocked: rounds_to_root_cause is None"
    transcript = result.get("transcript") or ""
    if not isinstance(transcript, str) or not transcript.strip():
        return None, None, "blocked: empty transcript"
    contamination_hits = list(result.get("contamination_hits") or [])
    contamination_hits.extend(scan_contamination(transcript))
    contamination_hits = sorted(set(contamination_hits))
    if contamination_hits:
        return None, None, "blocked_contaminated_run: " + ",".join(contamination_hits)
    case_id = result.get("case_id", "")
    case = case_map.get(case_id)
    if not case:
        return None, None, f"blocked: case {case_id} not found"
    pattern_id = case.get("reverse_from_pattern") or case.get("pattern_id")
    if not pattern_id:
        return None, None, f"blocked: case {case_id} has no reverse_from_pattern"
    transcript_hash = hashlib.sha256(transcript.encode()).hexdigest()
    if not SHA256_RE.fullmatch(transcript_hash):
        return None, None, "blocked: transcript_hash shape"
    artifact = _write_transcript(
        runs_dir, runner, case_id,
        bool(result.get("polaris_enabled")), transcript,
    )
    if not artifact.exists():
        return None, None, "blocked: artifact_path missing after write"
    model = os.environ.get("POLARIS_CLAUDE_MODEL") or os.environ.get("POLARIS_MODEL") or "unknown"
    evidence = {
        "agent": runner,
        "agent_version": "unknown",
        "model": model,
        "date_verified": _iso_now(),
        "status": "verified_live",
        "artifact_path": str(artifact.relative_to(REPO)),
        "transcript_hash": transcript_hash,
        "pre_failure_reproduced": True,
        "workdir_manifest_hash": workdir_manifest_hash,
        "notes": (
            f"case={case_id} polaris_enabled={bool(result.get('polaris_enabled'))} "
            f"rounds={metrics.get('rounds_to_root_cause')} "
            f"tool_calls={metrics.get('tool_calls', 0)} "
            f"tokens={metrics.get('token_consumption', 0)}"
        ),
    }
    return evidence, pattern_id, "ok"


def _load_shard(path: Path) -> dict:
    return json.loads(path.read_text())


def _save_shard(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2))


def _remove_from_candidate(pattern_id: str) -> Optional[Path]:
    shard_path = _find_shard(CANDIDATE, pattern_id)
    if shard_path is None:
        return None
    shard = _load_shard(shard_path)
    shard["records"] = [r for r in shard.get("records", [])
                         if r.get("pattern_id") != pattern_id]
    if shard["records"]:
        _save_shard(shard_path, shard)
    else:
        shard_path.unlink()
    return shard_path


def _promote_into_official(record: dict) -> Path:
    eco = record["ecosystem"]
    cls = record["error_class"]
    shard_dir = OFFICIAL / eco
    shard_dir.mkdir(parents=True, exist_ok=True)
    shard_path = shard_dir / f"{cls}.json"
    if shard_path.exists():
        shard = _load_shard(shard_path)
    else:
        shard = {"ecosystem": eco, "error_class": cls,
                 "schema_version": 4, "records": []}
    record = dict(record)
    record["source"] = "verified_candidate_promoted"
    review = [x for x in record.get("needs_human_review", []) if x != "agent_reproducibility"]
    record["needs_human_review"] = review
    shard["records"].append(record)
    _save_shard(shard_path, shard)
    return shard_path


def _append_evidence_to_record(shard_path: Path, pattern_id: str,
                                evidence: dict) -> str:
    """Return action tag: 'appended' | 'duplicate'."""
    shard = _load_shard(shard_path)
    for rec in shard.get("records", []):
        if rec.get("pattern_id") != pattern_id:
            continue
        ev_list = rec.setdefault("agent_reproducibility", {}).setdefault("evidence", [])
        for ev in ev_list:
            if (ev.get("agent") == evidence["agent"] and
                    ev.get("transcript_hash") == evidence["transcript_hash"]):
                return "duplicate"
        ev_list.append(evidence)
        review = rec.get("needs_human_review", [])
        rec["needs_human_review"] = [x for x in review if x != "agent_reproducibility"]
        _save_shard(shard_path, shard)
        return "appended"
    return "not_found"


def process_run(run_dir: Path) -> dict:
    results_path = run_dir / "results.json"
    if not results_path.exists():
        return {"error": f"missing {results_path}"}
    results = json.loads(results_path.read_text())
    case_map = _load_case_map()

    mock_ignored = 0
    blocked: list[dict] = []
    appended: list[dict] = []
    promoted: list[dict] = []
    duplicates: list[dict] = []

    for result in results:
        runner = result.get("runner_name", "")
        if runner == "mock":
            mock_ignored += 1
            continue
        evidence, pattern_id, reason = _evidence_from_result(
            result, case_map, run_dir,
        )
        if evidence is None:
            blocked.append({
                "runner": runner,
                "case_id": result.get("case_id"),
                "polaris_enabled": result.get("polaris_enabled"),
                "reason": reason,
            })
            continue

        shard_path, pool = _locate_pattern(pattern_id)
        if pool == "official":
            tag = _append_evidence_to_record(shard_path, pattern_id, evidence)
            if tag == "appended":
                appended.append({"pattern_id": pattern_id, "runner": runner,
                                 "case_id": result.get("case_id"),
                                 "transcript_hash": evidence["transcript_hash"]})
            elif tag == "duplicate":
                duplicates.append({"pattern_id": pattern_id, "runner": runner,
                                   "transcript_hash": evidence["transcript_hash"]})
            else:
                blocked.append({"runner": runner, "case_id": result.get("case_id"),
                                "reason": f"pattern {pattern_id} vanished mid-write"})
        elif pool == "candidate":
            cand_shard = _find_shard(CANDIDATE, pattern_id)
            cand = _load_shard(cand_shard)
            rec = next((r for r in cand["records"]
                        if r.get("pattern_id") == pattern_id), None)
            if rec is None:
                blocked.append({"runner": runner, "case_id": result.get("case_id"),
                                "reason": f"candidate {pattern_id} disappeared"})
                continue
            rec.setdefault("agent_reproducibility", {}).setdefault("evidence", []).append(evidence)
            promoted_shard = _promote_into_official(rec)
            _remove_from_candidate(pattern_id)
            promoted.append({
                "pattern_id": pattern_id,
                "from": str(cand_shard.relative_to(REPO)),
                "to": str(promoted_shard.relative_to(REPO)),
                "runner": runner,
                "case_id": result.get("case_id"),
                "transcript_hash": evidence["transcript_hash"],
            })
        else:
            blocked.append({"runner": runner, "case_id": result.get("case_id"),
                            "reason": f"pattern_id {pattern_id} not in any pool"})

    report = {
        "run_dir": str(run_dir.relative_to(REPO)),
        "mock_ignored_count": mock_ignored,
        "blocked_count": len(blocked),
        "blocked": blocked,
        "evidence_appended_count": len(appended),
        "evidence_appended": appended,
        "promoted_count": len(promoted),
        "promoted": promoted,
        "duplicate_skipped_count": len(duplicates),
        "duplicate_skipped": duplicates,
    }
    (REPO / "promotion-report-v4.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?", help="eval/runs/<ts> directory; defaults to latest")
    args = ap.parse_args()
    if args.run_dir:
        run_dir = Path(args.run_dir)
        if not run_dir.is_absolute():
            run_dir = REPO / run_dir
    else:
        runs = sorted((REPO / "eval" / "runs").glob("2*T*"))
        if not runs:
            print("no runs found", file=sys.stderr)
            return 2
        run_dir = runs[-1]
    print(f"[evidence_writer] processing {run_dir}")
    report = process_run(run_dir)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
