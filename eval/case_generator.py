# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Generate runnable cases + fixture manifests for every pattern with a
self-contained bash verification recipe.

A pattern is **auto-runnable** iff:
  - `shortest_verification.command` is non-empty
  - `shortest_verification.expected_stderr_match` is non-empty
  - `fix_path.fix_command` is non-empty

These are sufficient for the hermetic harness:
  pre_failure_command   = shortest_verification.command  (wrapped with cwd)
  expected_stderr_regex = shortest_verification.expected_stderr_match
  fix_command_test      = fix_path.fix_command

Cases that are NOT auto-runnable (missing any field) are emitted as skeletons
under `eval/generated-cases-v4/` with `blocked_reason=blocked_no_fixture`.

Runnable cases are written to:
  eval/cases/generated_<pattern_id>.json
with a peer manifest.json stored under `eval/fixtures/<case_id>/manifest.json`
(no files/ directory — bash-self-contained; the hermetic layer treats a missing
files/ as an empty workdir fixture).
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
OFFICIAL = REPO / "experience-packs-v4"
CANDIDATE = REPO / "experience-packs-v4-candidates"
CASES_DIR = REPO / "eval" / "cases"
FIX_DIR = REPO / "eval" / "fixtures"
OUT_SKELETONS = REPO / "eval" / "generated-cases-v4"
REPORT = REPO / "case-generation-report-v4.json"

EXISTING_AUTHORED = {
    "case_001_python_pythonpath", "case_002_node_enoent_lockfile",
    "case_003_docker_layer_cache", "case_004_python_syntax",
    "case_005_python_file_path", "case_006_node_fs_enoent",
}


def _safe_id(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", text).strip("_")


def _iter_records(root: Path, pool: str):
    for shard in sorted(root.rglob("*.json")):
        data = json.loads(shard.read_text())
        for rec in data.get("records", []):
            yield pool, shard, rec


def _authored_fixture_valid(rec: dict) -> bool:
    af = rec.get("authored_fixture")
    if not af:
        return False
    rr = af.get("reviewer_record") or {}
    return (
        rr.get("sandbox_pre_fix_exit_code") not in (None, 0)
        and rr.get("sandbox_pre_fix_stderr_match")
        and rr.get("sandbox_post_fix_exit_code") == 0
    )


def _generate_runnable_case(pool: str, rec: dict) -> tuple[dict, dict, list[dict]] | None:
    """Return (case_json, manifest_json, fixture_files) if auto-runnable.

    When the pattern carries a sandbox-validated authored_fixture, it drives
    the case: real project files go to the fixture workdir, the authored
    verification_command is run pre- and post-agent, and the post-fix check
    re-runs the same verification_command (it must now exit 0). The ascent
    from pattern → case never synthesizes a shell echo as the ground-truth
    signal; only a real verification tool exit code does.
    """
    pid = rec["pattern_id"]
    case_id = f"generated_{_safe_id(pid)}"
    ecosystem = rec["ecosystem"]
    error_class = rec["error_class"]
    description = rec.get("description", pid)

    if _authored_fixture_valid(rec):
        af = rec["authored_fixture"]
        fixture_files = list(af["files"])
        verification_command = af["verification_command"]
        expected_rx = af["expected_stderr_regex"]
        pre_failure = f"cd {{workdir}} && {verification_command}"
        fix_test = pre_failure  # post-fix gate == same verification_command, now must exit 0
        initial_prompt = (
            f"In the project at {{workdir}}, this {ecosystem} {error_class} "
            f"fails: {description}. Reproduce the failure with "
            f"`{verification_command}`, diagnose the root cause by reading the "
            "project files, and apply a fix so that same command exits 0."
        )
        case_json = {
            "case_id": case_id,
            "source": "authored_fixture",
            "reverse_from_pattern": pid if pool == "official" else None,
            "pattern_id": pid,
            "source_pool": pool,
            "ecosystem": ecosystem,
            "error_class": error_class,
            "initial_prompt": initial_prompt,
            "success_criteria": {
                "root_cause_regex": ".+",
                "fix_command_test": fix_test,
            },
            "max_rounds": 6,
            "fixture_strategy": "authored_files",
            "promotion_eligible": True,
        }
        manifest_json = {
            "case_id": case_id,
            "files": [f["path"] for f in fixture_files],
            "dependencies": {},
            "build_commands": [],
            "expected_failure_command": pre_failure,
            "expected_failure_stderr_regex": expected_rx,
            "manifest_schema_version": 1,
            "bash_self_contained": False,
            "reverse_from_pattern": pid,
            "source_pool": pool,
        }
        return case_json, manifest_json, fixture_files

    # Fallback: no authored fixture. Do NOT generate a case from synthetic
    # shortest_verification / fix_command — those recipes were already
    # flagged as contamination-by-construction (see pattern_schema).
    return None


def _write_case(case_json: dict, manifest_json: dict, fixture_files: list[dict] | None = None) -> None:
    case_id = case_json["case_id"]
    (CASES_DIR / f"{case_id}.json").write_text(json.dumps(case_json, indent=2))
    case_fix_dir = FIX_DIR / case_id
    case_fix_dir.mkdir(parents=True, exist_ok=True)
    (case_fix_dir / "manifest.json").write_text(json.dumps(manifest_json, indent=2))
    if fixture_files:
        files_dir = case_fix_dir / "files"
        if files_dir.exists():
            shutil.rmtree(files_dir)
        files_dir.mkdir(parents=True, exist_ok=True)
        for f in fixture_files:
            p = files_dir / f["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f["content"])


def main() -> int:
    if OUT_SKELETONS.exists():
        shutil.rmtree(OUT_SKELETONS)
    OUT_SKELETONS.mkdir(parents=True, exist_ok=True)

    # Sweep any prior generated case files before regenerating.
    for p in CASES_DIR.glob("generated_*.json"):
        p.unlink()
    for d in FIX_DIR.iterdir():
        if d.is_dir() and d.name.startswith("generated_"):
            shutil.rmtree(d)

    totals = {
        "official_schema_valid_count": 0,
        "candidate_schema_valid_count": 0,
        "total_schema_valid_pool": 0,
        "runnable_case_count": 0,
        "blocked_no_fixture_count": 0,
        "per_pool_runnable": {"official": 0, "candidate": 0},
        "per_pool_blocked": {"official": 0, "candidate": 0},
        "per_ecosystem_runnable": {},
        "per_ecosystem_blocked": {},
        "blocked_reasons": {
            "missing_verification_command": 0,
            "missing_expected_stderr": 0,
            "missing_fix_command": 0,
        },
    }
    blocked_samples = []

    def _count_blocked(rec: dict, pool: str, eco: str) -> None:
        sv = rec.get("shortest_verification") or {}
        fp = rec.get("fix_path") or {}
        if not (sv.get("command") or "").strip():
            totals["blocked_reasons"]["missing_verification_command"] += 1
        if not (sv.get("expected_stderr_match") or "").strip():
            totals["blocked_reasons"]["missing_expected_stderr"] += 1
        if not (fp.get("fix_command") or "").strip():
            totals["blocked_reasons"]["missing_fix_command"] += 1
        totals["blocked_reasons"].setdefault("missing_authored_fixture", 0)
        if not _authored_fixture_valid(rec):
            totals["blocked_reasons"]["missing_authored_fixture"] += 1
        if len(blocked_samples) < 12:
            blocked_samples.append({
                "pattern_id": rec["pattern_id"],
                "source_pool": pool,
                "authored_fixture_valid": _authored_fixture_valid(rec),
                "has_command": bool((sv.get("command") or "").strip()),
                "has_stderr_regex": bool((sv.get("expected_stderr_match") or "").strip()),
                "has_fix_command": bool((fp.get("fix_command") or "").strip()),
            })

    for pool, _shard, rec in list(_iter_records(OFFICIAL, "official")) + list(_iter_records(CANDIDATE, "candidate")):
        eco = rec["ecosystem"]
        if pool == "official":
            totals["official_schema_valid_count"] += 1
        else:
            totals["candidate_schema_valid_count"] += 1

        built = _generate_runnable_case(pool, rec)
        if built:
            case_json, manifest_json, fixture_files = built
            _write_case(case_json, manifest_json, fixture_files)
            totals["runnable_case_count"] += 1
            totals["per_pool_runnable"][pool] += 1
            totals["per_ecosystem_runnable"][eco] = totals["per_ecosystem_runnable"].get(eco, 0) + 1
        else:
            totals["blocked_no_fixture_count"] += 1
            totals["per_pool_blocked"][pool] += 1
            totals["per_ecosystem_blocked"][eco] = totals["per_ecosystem_blocked"].get(eco, 0) + 1
            _count_blocked(rec, pool, eco)
            # Skeleton for audit trail.
            out_dir = OUT_SKELETONS / pool / eco
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{_safe_id(rec['pattern_id'])}.json").write_text(
                json.dumps({
                    "pattern_id": rec["pattern_id"],
                    "source_pool": pool,
                    "blocked_reason": "blocked_no_auto_fixture",
                    "has_verification_command": bool((rec.get("shortest_verification") or {}).get("command")),
                    "has_stderr_regex": bool((rec.get("shortest_verification") or {}).get("expected_stderr_match")),
                    "has_fix_command": bool((rec.get("fix_path") or {}).get("fix_command")),
                }, indent=2)
            )

    totals["total_schema_valid_pool"] = (
        totals["official_schema_valid_count"] + totals["candidate_schema_valid_count"]
    )
    report = {
        **totals,
        "existing_authored_fixtures": sorted(EXISTING_AUTHORED),
        "blocked_samples": blocked_samples,
        "note": (
            "Runnable cases use the pattern's own shortest_verification.command "
            "(pre-failure check) and fix_path.fix_command (post-fix check). "
            "A pattern is auto-runnable iff both are present. Candidate pool "
            "records currently have NO fix_command, so they are all blocked; "
            "the v4 candidate harvester generated them from trigger signals "
            "only. Promoting candidates requires authoring a fix_command per "
            "record — by hand or by running a real-agent pass that infers one."
        ),
    }
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
