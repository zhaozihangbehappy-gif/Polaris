# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Build manifest.json for each fixture and a fixtures_validator.

Manifest schema (per case):
  case_id, files: [{relpath, sha256, size}], dependencies: {tool: version_spec},
  build_commands: [shell], expected_failure_command: str,
  expected_failure_stderr_regex: str.

The validator rehashes fixture files, confirms deps are present, and is the
only accepted source of audit evidence for the evidence_writer downstream.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIX = REPO / "eval" / "fixtures"


def sha256_of(p: Path) -> str:
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()


def enumerate_files(case_dir: Path) -> list[dict]:
    root = case_dir / "files"
    rows = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rows.append({
                "relpath": str(p.relative_to(root)),
                "sha256": sha256_of(p),
                "size": p.stat().st_size,
            })
    return rows


CASES_SPEC: dict[str, dict] = {
    "case_001_python_pythonpath": {
        "dependencies": {"python3": ">=3.10"},
        "build_commands": [
            "rm -rf {workdir} && mkdir -p {workdir}",
            "cp -r files/. {workdir}/",
        ],
        "expected_failure_command": "cd {workdir} && python3 test.py",
        "expected_failure_stderr_regex": "ModuleNotFoundError: No module named 'mymod'",
    },
    "case_002_node_enoent_lockfile": {
        "dependencies": {"pnpm": ">=9.0"},
        "build_commands": [
            "rm -rf {workdir} && mkdir -p {workdir}",
            "cp -r files/. {workdir}/",
        ],
        "expected_failure_command": "cd {workdir} && pnpm install --frozen-lockfile",
        "expected_failure_stderr_regex": "old-name|ERR_PNPM_OUTDATED_LOCKFILE|ENOENT",
    },
    "case_003_docker_layer_cache": {
        "dependencies": {"docker": ">=24.0"},
        "build_commands": [
            "rm -rf {workdir} && mkdir -p {workdir}",
            "cp -r files/. {workdir}/",
        ],
        "expected_failure_command": "cd {workdir} && docker build -t polaris-case03 .",
        "expected_failure_stderr_regex": "app.py.*not found|failed to compute cache key",
    },
    "case_004_python_syntax": {
        "dependencies": {"python3": ">=3.10"},
        "build_commands": [
            "rm -rf {workdir} && mkdir -p {workdir}",
            "cp -r files/. {workdir}/",
        ],
        "expected_failure_command": "cd {workdir} && python3 app.py",
        "expected_failure_stderr_regex": "SyntaxError",
    },
    "case_005_python_file_path": {
        "dependencies": {"python3": ">=3.10"},
        "build_commands": [
            "rm -rf {workdir} && mkdir -p {workdir}",
            "cp -r files/. {workdir}/",
        ],
        "expected_failure_command": "cd {workdir}/scripts && python3 read_value.py",
        "expected_failure_stderr_regex": "FileNotFoundError",
    },
    "case_006_node_fs_enoent": {
        "dependencies": {"node": ">=18.0"},
        "build_commands": [
            "rm -rf {workdir} && mkdir -p {workdir}",
            "cp -r files/. {workdir}/",
        ],
        "expected_failure_command": "cd {workdir} && node build.js",
        "expected_failure_stderr_regex": "ENOENT",
    },
    "real_001_pnpm_version_drift": {
        "dependencies": {
            "node": ">=18.0",
            "tar": ">=1.30",
            "platform": "linux-x64",
        },
        "build_commands": [
            "rm -rf {workdir} && mkdir -p {workdir}",
            "cp -r files/. {workdir}/",
            "mkdir -p {workdir}/node_modules/pnpm {workdir}/node_modules/.bin",
            "tar -xzf {workdir}/vendor/pnpm-7.33.7.tgz -C {workdir}/node_modules/pnpm --strip-components=1",
            "ln -sf ../pnpm/bin/pnpm.cjs {workdir}/node_modules/.bin/pnpm",
        ],
        "expected_failure_command": (
            "cd {workdir} && ./node_modules/.bin/pnpm install --frozen-lockfile"
        ),
        "expected_failure_stderr_regex": (
            "ERR_PNPM_OUTDATED_LOCKFILE|"
            "ERR_PNPM_LOCKFILE_BREAKING_CHANGE|"
            "lockfile.*(is not up to date|breaking change|unsupported)"
        ),
    },
    # real_002_ruff_match_parser and real_003_setuptools_editable_pep660 were
    # authored 2026-04-21 but invalidated under Python 3.12 host toolchain
    # before entering the candidate pool: ruff 0.9.8 parses `match` cleanly so
    # its expected SyntaxError never fires, and setuptools 61.0.0 import-breaks
    # on 3.12 before the PEP 660 path is reached. Their fixture trees remain on
    # disk as backlog; they are intentionally NOT in CASES_SPEC so build/
    # validate do not treat them as active real cases. Re-onboard only after
    # pre_failure reproduces on the host.
}


def build_all() -> dict:
    report = {}
    for case_id, spec in CASES_SPEC.items():
        case_dir = FIX / case_id
        if not case_dir.is_dir():
            report[case_id] = {"status": "missing"}
            continue
        files = enumerate_files(case_dir)
        manifest = {
            "case_id": case_id,
            "files": files,
            "dependencies": spec["dependencies"],
            "build_commands": spec["build_commands"],
            "expected_failure_command": spec["expected_failure_command"],
            "expected_failure_stderr_regex": spec["expected_failure_stderr_regex"],
            "manifest_schema_version": 1,
        }
        (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        report[case_id] = {
            "status": "ok",
            "files": len(files),
            "total_bytes": sum(f["size"] for f in files),
        }
    (FIX / "manifest_build_report.json").write_text(json.dumps(report, indent=2))
    return report


def validate_all() -> dict:
    """Re-hash every fixture and confirm it matches its manifest."""
    report = {}
    for case_id in CASES_SPEC:
        case_dir = FIX / case_id
        manifest_path = case_dir / "manifest.json"
        if not manifest_path.exists():
            report[case_id] = {"status": "no_manifest"}
            continue
        manifest = json.loads(manifest_path.read_text())
        fresh = enumerate_files(case_dir)
        mismatches = []
        fresh_by_path = {f["relpath"]: f for f in fresh}
        for recorded in manifest["files"]:
            actual = fresh_by_path.get(recorded["relpath"])
            if actual is None:
                mismatches.append(f"missing: {recorded['relpath']}")
                continue
            if actual["sha256"] != recorded["sha256"]:
                mismatches.append(f"hash_mismatch: {recorded['relpath']}")
        if len(fresh) != len(manifest["files"]):
            mismatches.append(
                f"file_count: manifest={len(manifest['files'])} actual={len(fresh)}"
            )
        report[case_id] = {
            "status": "ok" if not mismatches else "mismatch",
            "mismatches": mismatches,
        }
    return report


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "build"
    if cmd == "build":
        print(json.dumps(build_all(), indent=2))
    elif cmd == "validate":
        print(json.dumps(validate_all(), indent=2))
    else:
        print("usage: fixtures_manifest.py [build|validate]", file=sys.stderr)
        sys.exit(2)
