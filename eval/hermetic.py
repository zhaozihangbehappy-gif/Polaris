"""Hermetic per-variant workdir preparation for the Polaris evaluation harness.

For every (runner, case, variant) tuple the orchestrator allocates a fresh
workdir, copies the fixture files into it, runs the case's
`expected_failure_command`, and confirms the stderr matches
`expected_failure_stderr_regex`. Evidence can only be harvested from runs
where `pre_failure_reproduced == True`.

All templated fields in the case manifest use the placeholder `{workdir}` which
is substituted with the absolute path of the variant workdir at run time.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


REPO = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO / "eval" / "fixtures"
RUNS_ROOT = Path("/tmp/_polaris_runs")


def substitute(text: str, workdir: Path) -> str:
    return (text or "").replace("{workdir}", str(workdir))


@dataclass
class HermeticContext:
    workdir: Path
    workdir_manifest_hash: str
    fixture_present: bool
    fixture_reason: str
    expected_failure_command: str
    expected_failure_stderr_regex: str
    pre_failure_command: str
    pre_failure_output: str
    pre_failure_reproduced: bool
    initial_prompt_substituted: str
    fix_command_test_substituted: str
    blocked_reason: Optional[str] = None

    def to_public_dict(self) -> dict:
        return {
            "workdir": str(self.workdir),
            "workdir_manifest_hash": self.workdir_manifest_hash,
            "fixture_present": self.fixture_present,
            "fixture_reason": self.fixture_reason,
            "pre_failure_command": self.pre_failure_command,
            "pre_failure_output": self.pre_failure_output[-4000:],
            "pre_failure_reproduced": self.pre_failure_reproduced,
            "blocked_reason": self.blocked_reason,
        }


def _hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    if not root.exists():
        return ""
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def _load_manifest(case_id: str) -> Optional[dict]:
    mp = FIXTURES_DIR / case_id / "manifest.json"
    if not mp.exists():
        return None
    try:
        return json.loads(mp.read_text())
    except json.JSONDecodeError:
        return None


def _copy_fixture(case_id: str, workdir: Path) -> tuple[bool, str]:
    src = FIXTURES_DIR / case_id / "files"
    workdir.mkdir(parents=True, exist_ok=True)
    for child in workdir.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
    if not src.is_dir():
        # Bash-self-contained pattern: no repo files needed. The expected_failure
        # command generates its own stderr; an empty workdir is a valid fixture.
        return True, "bash_self_contained"
    shutil.copytree(src, workdir, dirs_exist_ok=True)
    return True, "ok"


def prepare_variant_workdir(
    run_id: str,
    runner_name: str,
    case_id: str,
    variant: str,
    case: dict,
) -> HermeticContext:
    """Return a HermeticContext for one (runner, case, variant). If the fixture
    is missing, or `expected_failure_command` doesn't reproduce the bad state,
    the context's `blocked_reason` is set and no agent should be invoked."""
    workdir = RUNS_ROOT / run_id / runner_name / case_id / variant
    manifest = _load_manifest(case_id)
    fixture_present, fixture_reason = _copy_fixture(case_id, workdir)
    workdir_hash = _hash_tree(workdir)

    # Substitute placeholder on every relevant field.
    prompt = substitute(case.get("initial_prompt", ""), workdir)
    fix_cmd = substitute(
        (case.get("success_criteria") or {}).get("fix_command_test", ""), workdir
    )
    expected_cmd_tpl = ""
    expected_rx = ""
    if manifest:
        expected_cmd_tpl = manifest.get("expected_failure_command", "") or ""
        expected_rx = manifest.get("expected_failure_stderr_regex", "") or ""
    pre_cmd = substitute(expected_cmd_tpl, workdir)

    if not fixture_present:
        return HermeticContext(
            workdir=workdir,
            workdir_manifest_hash=workdir_hash,
            fixture_present=False,
            fixture_reason=fixture_reason,
            expected_failure_command=pre_cmd,
            expected_failure_stderr_regex=expected_rx,
            pre_failure_command=pre_cmd,
            pre_failure_output="",
            pre_failure_reproduced=False,
            initial_prompt_substituted=prompt,
            fix_command_test_substituted=fix_cmd,
            blocked_reason="blocked_no_fixture",
        )

    if not pre_cmd or not expected_rx:
        return HermeticContext(
            workdir=workdir,
            workdir_manifest_hash=workdir_hash,
            fixture_present=True,
            fixture_reason="ok",
            expected_failure_command=pre_cmd,
            expected_failure_stderr_regex=expected_rx,
            pre_failure_command=pre_cmd,
            pre_failure_output="",
            pre_failure_reproduced=False,
            initial_prompt_substituted=prompt,
            fix_command_test_substituted=fix_cmd,
            blocked_reason="blocked_no_expected_failure",
        )

    try:
        proc = subprocess.run(
            ["bash", "-c", pre_cmd],
            capture_output=True, text=True, timeout=90,
        )
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = f"[pre_failure timeout] {e}"
        return HermeticContext(
            workdir=workdir,
            workdir_manifest_hash=workdir_hash,
            fixture_present=True,
            fixture_reason="ok",
            expected_failure_command=pre_cmd,
            expected_failure_stderr_regex=expected_rx,
            pre_failure_command=pre_cmd,
            pre_failure_output=out,
            pre_failure_reproduced=False,
            initial_prompt_substituted=prompt,
            fix_command_test_substituted=fix_cmd,
            blocked_reason="blocked_precondition_timeout",
        )

    reproduced = bool(re.search(expected_rx, out))
    return HermeticContext(
        workdir=workdir,
        workdir_manifest_hash=workdir_hash,
        fixture_present=True,
        fixture_reason="ok",
        expected_failure_command=pre_cmd,
        expected_failure_stderr_regex=expected_rx,
        pre_failure_command=pre_cmd,
        pre_failure_output=out,
        pre_failure_reproduced=reproduced,
        initial_prompt_substituted=prompt,
        fix_command_test_substituted=fix_cmd,
        blocked_reason=None if reproduced else "blocked_precondition_failed",
    )


CONTAMINATION_PHRASES = [
    "already fixed",
    "already passes",
    "already passing",
    "no edits needed",
    "nothing to fix",
    "failure does not reproduce",
    "bad state is not reproduced",
    "bad state does not reproduce",
    "no changes needed",
    "no action required",
]


def scan_contamination(transcript: str) -> list[str]:
    if not transcript:
        return []
    low = transcript.lower()
    return [p for p in CONTAMINATION_PHRASES if p in low]
