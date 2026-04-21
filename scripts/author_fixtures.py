"""Author real failing-project fixtures for every v4 pattern using Codex.

For each schema-valid pattern:
  1. Compose an authoring prompt from (ecosystem, error_class, description,
     trigger_signals.stderr_regex) and a rigid output contract.
  2. Invoke `codex exec --json --full-auto --skip-git-repo-check` inside a
     scratch workdir `/tmp/polaris_authoring/<pattern_id>/`.
  3. Read the sidecar `authored.json` Codex was required to produce.
  4. Sandbox-validate in two fresh dirs:
       sandbox_pre/  — files[] written, verification_command must FAIL and
                       stderr must match expected_stderr_regex.
       sandbox_post/ — reference_fix_files[] written, verification_command
                       must PASS (exit 0).
  5. If both pass, merge an `authored_fixture` block (with reviewer_record) into
     the pattern shard on disk; set status-ish markers accordingly.

Ecosystems whose toolchains are not available in this environment (go, ruby,
java, docker, terraform) are short-circuited with reason
`authoring_blocked_tooling_unavailable` — no Codex call is made and no fake
fixture is recorded.

Parallelism: a thread pool with BATCH_WORKERS workers. Each pattern is atomic
(independent workdir, independent shard write under a per-shard lock).

Resume-ability: patterns that already carry a sandbox-valid authored_fixture
are skipped.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OFFICIAL = REPO / "experience-packs-v4"
CANDIDATE = REPO / "experience-packs-v4-candidates"
AUTH_ROOT = Path("/tmp/polaris_authoring")
SANDBOX_ROOT = Path("/tmp/polaris_authoring_sandbox")
LOG_ROOT = REPO / "authoring_logs"
REPORT = REPO / "authoring_report.json"

# Ecosystems with working real toolchains in this environment.
SANDBOXABLE_ECOSYSTEMS = {"python", "node", "rust", "go", "java"}
# docker: daemon sock perm — needs `usermod -aG docker $USER` + session reload.
# ruby, terraform: toolchain install pending.

AUTHORING_TIMEOUT_S = 300
SANDBOX_TIMEOUT_S = 90
BATCH_WORKERS = int(os.environ.get("POLARIS_AUTHORING_WORKERS", "4"))

_shard_locks: dict[str, threading.Lock] = {}
_shard_locks_guard = threading.Lock()


def _shard_lock(path: Path) -> threading.Lock:
    with _shard_locks_guard:
        lk = _shard_locks.get(str(path))
        if lk is None:
            lk = threading.Lock()
            _shard_locks[str(path)] = lk
        return lk


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def _hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    if not root.exists():
        return ""
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(b"\0")
            try:
                h.update(p.read_bytes())
            except OSError:
                pass
            h.update(b"\0")
    return h.hexdigest()


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


AUTHOR_PROMPT_TEMPLATE = """You are authoring a minimal failing software project so a coding agent can later be tested on fixing it.

Context (Polaris pattern):
  pattern_id: {pattern_id}
  ecosystem:  {ecosystem}
  error_class: {error_class}
  description: {description}
  stderr regex (from pattern): {stderr_regex}

Your deliverable: write a small, self-contained project in THIS DIRECTORY that exhibits a real failure matching the pattern. The failure must come from a real tool ({ecosystem_tools}), not from `echo` / `printf` / `|| true`.

Also write a machine-readable sidecar `authored.json` at the project root with this EXACT shape:
{{
  "verification_command": "<shell command run from project root; exits non-zero now and zero after the fix>",
  "expected_stderr_regex": "<regex matching the current failure's stderr>",
  "files": [{{"path": "<relative>", "content": "<full text>"}}, ...],
  "reference_fix_files": [{{"path": "<relative>", "content": "<full text>"}}, ...],
  "fix_rationale": "<one sentence>"
}}

Hard rules:
  - Keep the project tiny: ≤6 files, ≤200 LOC total, no external package installs (use only the standard library of {ecosystem}).
  - `verification_command` MUST be deterministic AND must have its exit code be a genuine function of the code on disk. No `|| true`, no `echo ... exit N`.
  - `files[]` is what is on disk right now (the failing state). `reference_fix_files[]` is what a correct fix would look like (full content of any modified file; unchanged files may be omitted).
  - `expected_stderr_regex` must actually match the stderr that `verification_command` emits in the failing state.
  - After the fix (content replaced per reference_fix_files) the verification_command must exit 0.

Emit ONLY the project files and authored.json. When done, print exactly "AUTHORED" on its own line and stop."""


ECOSYSTEM_TOOLS = {
    "python": "python3, python -m compileall, pytest via `python3 -m unittest`",
    "node": "node, npm test via `node --test` or plain `node script.js`",
    "rust": "cargo (use `cargo check` or `cargo test`)",
    "go": "go (go build / go test)",
    "ruby": "ruby (ruby script.rb or `ruby -Ilib -e ...`)",
    "java": "javac + java (no maven/gradle)",
    "docker": "docker build / docker run (avoid network)",
    "terraform": "terraform init / terraform plan",
}


def _build_prompt(rec: dict) -> tuple[str, str]:
    sr = (rec.get("trigger_signals") or {}).get("stderr_regex") or []
    stderr_regex = sr[0] if sr else ".*"
    body = AUTHOR_PROMPT_TEMPLATE.format(
        pattern_id=rec["pattern_id"],
        ecosystem=rec["ecosystem"],
        error_class=rec["error_class"],
        description=rec.get("description", ""),
        stderr_regex=stderr_regex,
        ecosystem_tools=ECOSYSTEM_TOOLS.get(rec["ecosystem"], "any standard tool"),
    )
    return body, _sha256(body)


def _run_codex_author(workdir: Path, prompt: str, log_path: Path) -> dict:
    cmd = [
        "codex", "exec",
        "--json",
        "--full-auto",
        "--skip-git-repo-check",
        "-c", 'approval_policy="never"',
        "-C", str(workdir),
        prompt,
    ]
    return _run_subprocess_author(cmd, workdir, log_path, tag="codex")


def _run_claude_code_author(workdir: Path, prompt: str, log_path: Path) -> dict:
    cmd = [
        "claude", "-p",
        "--dangerously-skip-permissions",
        "--add-dir", str(workdir),
        "--output-format", "text",
        prompt,
    ]
    model = os.environ.get("POLARIS_AUTHOR_CLAUDE_MODEL")
    if model:
        cmd[3:3] = ["--model", model]
    budget = os.environ.get("POLARIS_AUTHOR_CLAUDE_MAX_BUDGET_USD")
    if budget:
        cmd[3:3] = ["--max-budget-usd", budget]
    return _run_subprocess_author(cmd, workdir, log_path, tag="claude_code")


def _run_subprocess_author(cmd: list[str], workdir: Path, log_path: Path, tag: str) -> dict:
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True,
            timeout=AUTHORING_TIMEOUT_S,
            cwd=str(workdir),
        )
        elapsed = time.monotonic() - start
        log_path.write_text(
            f"[backend={tag} exit={proc.returncode} elapsed={elapsed:.1f}s]\n"
            f"[stdout]\n{proc.stdout[-40000:]}\n"
            f"[stderr]\n{proc.stderr[-10000:]}\n"
        )
        return {"returncode": proc.returncode, "stdout": proc.stdout, "stderr": proc.stderr, "elapsed": elapsed}
    except subprocess.TimeoutExpired as e:
        elapsed = time.monotonic() - start
        log_path.write_text(f"[backend={tag} timeout elapsed={elapsed:.1f}s]\n{e}")
        return {"returncode": -1, "stdout": "", "stderr": f"timeout after {elapsed:.1f}s", "elapsed": elapsed}


_AUTHORING_BACKENDS = {
    "codex": _run_codex_author,
    "claude_code": _run_claude_code_author,
}


def _parse_authored(workdir: Path) -> tuple[dict | None, str]:
    sidecar = workdir / "authored.json"
    if not sidecar.exists():
        return None, "authored.json missing from workdir"
    try:
        d = json.loads(sidecar.read_text())
    except Exception as e:
        return None, f"authored.json invalid JSON: {e}"
    required = {"verification_command", "expected_stderr_regex", "files", "reference_fix_files"}
    missing = required - set(d.keys())
    if missing:
        return None, f"authored.json missing keys: {sorted(missing)}"
    for key in ("files", "reference_fix_files"):
        if not isinstance(d[key], list) or not d[key]:
            return None, f"{key} must be a non-empty list"
        for i, f in enumerate(d[key]):
            if not isinstance(f, dict) or "path" not in f or "content" not in f:
                return None, f"{key}[{i}] must have path+content"
    return d, "ok"


def _write_files(dst: Path, files: list[dict]) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for f in files:
        p = dst / f["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f["content"])


def _sandbox_run(cmd: str, cwd: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["bash", "-c", cmd],
            capture_output=True, text=True,
            timeout=SANDBOX_TIMEOUT_S,
            cwd=str(cwd),
        )
        return proc.returncode, (proc.stdout or "") + "\n" + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"[timeout after {SANDBOX_TIMEOUT_S}s]"


def _sandbox_validate(pattern_id: str, authored: dict) -> dict:
    pre = SANDBOX_ROOT / pattern_id / "pre"
    post = SANDBOX_ROOT / pattern_id / "post"
    for d in (pre, post):
        if d.exists():
            shutil.rmtree(d)
    _write_files(pre, authored["files"])
    # reference_fix_files is layered on top of files in post (fix is a diff)
    _write_files(post, authored["files"])
    _write_files(post, authored["reference_fix_files"])
    pre_hash = _hash_tree(pre)
    post_hash = _hash_tree(post)
    vcmd = authored["verification_command"]
    rx = authored["expected_stderr_regex"]
    pre_rc, pre_out = _sandbox_run(vcmd, pre)
    post_rc, post_out = _sandbox_run(vcmd, post)
    stderr_match = bool(re.search(rx, pre_out))
    return {
        "sandbox_pre_fix_exit_code": pre_rc,
        "sandbox_pre_fix_stderr_match": stderr_match,
        "sandbox_post_fix_exit_code": post_rc,
        "sandbox_workdir_hash_pre": pre_hash,
        "sandbox_workdir_hash_post": post_hash,
        "sandbox_pre_output_tail": pre_out[-1000:],
        "sandbox_post_output_tail": post_out[-1000:],
    }


def _merge_authored_into_shard(shard_path: Path, pattern_id: str, block: dict) -> None:
    with _shard_lock(shard_path):
        data = json.loads(shard_path.read_text())
        for rec in data.get("records", []):
            if rec.get("pattern_id") == pattern_id:
                rec["authored_fixture"] = block
                break
        shard_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _existing_authored_is_valid(rec: dict) -> bool:
    af = rec.get("authored_fixture")
    if not af:
        return False
    rr = af.get("reviewer_record") or {}
    return (
        rr.get("sandbox_pre_fix_exit_code") not in (None, 0)
        and rr.get("sandbox_pre_fix_stderr_match")
        and rr.get("sandbox_post_fix_exit_code") == 0
    )


def _author_one(shard_path: Path, rec: dict, backend: str = "codex") -> dict:
    pid = rec["pattern_id"]
    eco = rec["ecosystem"]
    out: dict = {"pattern_id": pid, "ecosystem": eco, "shard": str(shard_path.relative_to(REPO)), "backend": backend}

    if _existing_authored_is_valid(rec):
        out["status"] = "skipped_already_authored"
        return out

    if eco not in SANDBOXABLE_ECOSYSTEMS:
        out["status"] = "authoring_blocked_tooling_unavailable"
        out["reason"] = f"ecosystem {eco} has no working toolchain in this environment"
        return out

    wd = AUTH_ROOT / pid
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True, exist_ok=True)
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    log_path = LOG_ROOT / f"{pid}.{backend}.log"

    prompt, prompt_sha = _build_prompt(rec)
    runner = _AUTHORING_BACKENDS[backend]
    run_result = runner(wd, prompt, log_path)
    if run_result["returncode"] != 0:
        out["status"] = "authoring_failed"
        out["reason"] = f"{backend} exit={run_result['returncode']}, stderr tail: {run_result['stderr'][-300:]}"
        return out

    authored, parse_msg = _parse_authored(wd)
    if authored is None:
        out["status"] = "authoring_failed"
        out["reason"] = f"sidecar parse: {parse_msg}"
        return out

    try:
        sandbox = _sandbox_validate(pid, authored)
    except Exception as e:
        out["status"] = "authoring_failed"
        out["reason"] = f"sandbox exception: {e}"
        return out

    valid = (
        sandbox["sandbox_pre_fix_exit_code"] != 0
        and sandbox["sandbox_pre_fix_stderr_match"]
        and sandbox["sandbox_post_fix_exit_code"] == 0
    )
    if not valid:
        out["status"] = "sandbox_invalid"
        out["reason"] = (
            f"pre_rc={sandbox['sandbox_pre_fix_exit_code']} "
            f"stderr_match={sandbox['sandbox_pre_fix_stderr_match']} "
            f"post_rc={sandbox['sandbox_post_fix_exit_code']}"
        )
        out["sandbox_detail"] = sandbox
        return out

    block = {
        "authored_at": _now(),
        "authored_by": backend,
        "authored_with_prompt_sha256": prompt_sha,
        "verification_command": authored["verification_command"],
        "expected_stderr_regex": authored["expected_stderr_regex"],
        "files": authored["files"],
        "reference_fix_files": authored["reference_fix_files"],
        "fix_rationale": authored.get("fix_rationale", ""),
        "reviewer_record": {
            "validated_in_sandbox_at": _now(),
            "sandbox_pre_fix_exit_code": sandbox["sandbox_pre_fix_exit_code"],
            "sandbox_pre_fix_stderr_match": sandbox["sandbox_pre_fix_stderr_match"],
            "sandbox_post_fix_exit_code": sandbox["sandbox_post_fix_exit_code"],
            "sandbox_workdir_hash_pre": sandbox["sandbox_workdir_hash_pre"],
            "sandbox_workdir_hash_post": sandbox["sandbox_workdir_hash_post"],
            "notes": f"authored by {backend}; pre-fix fails+matches regex, post-fix passes",
        },
    }
    _merge_authored_into_shard(shard_path, pid, block)
    out["status"] = "authored_fixture_candidate"
    return out


def _iter_targets(include_candidates: bool, ecosystems: set[str] | None, limit: int | None, pattern_ids: set[str] | None = None):
    roots = [OFFICIAL] + ([CANDIDATE] if include_candidates else [])
    seen = 0
    for root in roots:
        for shard_path in sorted(root.rglob("*.json")):
            data = json.loads(shard_path.read_text())
            for rec in data.get("records", []):
                if ecosystems and rec.get("ecosystem") not in ecosystems:
                    continue
                if pattern_ids and rec.get("pattern_id") not in pattern_ids:
                    continue
                if limit is not None and seen >= limit:
                    return
                yield shard_path, rec
                seen += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--ecosystems", type=str, default=None, help="comma-separated filter")
    ap.add_argument("--candidates", action="store_true", help="include candidate pool")
    ap.add_argument("--workers", type=int, default=BATCH_WORKERS)
    ap.add_argument("--only-sandboxable", action="store_true",
                    help="skip ecosystems with no real toolchain in this env")
    ap.add_argument("--backend", choices=sorted(_AUTHORING_BACKENDS.keys()), default="codex",
                    help="authoring backend: codex (default) or claude_code")
    ap.add_argument("--pattern-ids", type=str, default=None,
                    help="comma-separated pattern_id whitelist (retry failed subset)")
    args = ap.parse_args()

    ecos = set(args.ecosystems.split(",")) if args.ecosystems else None
    if args.only_sandboxable:
        ecos = (ecos or set(ECOSYSTEM_TOOLS.keys())) & SANDBOXABLE_ECOSYSTEMS
    pids = set(args.pattern_ids.split(",")) if args.pattern_ids else None
    targets = list(_iter_targets(args.candidates, ecos, args.limit, pids))
    print(f"[author_fixtures] targets={len(targets)} workers={args.workers}")

    AUTH_ROOT.mkdir(parents=True, exist_ok=True)
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        fut_map = {ex.submit(_author_one, shard, rec, args.backend): rec["pattern_id"] for shard, rec in targets}
        for i, fut in enumerate(as_completed(fut_map), 1):
            pid = fut_map[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = {"pattern_id": pid, "status": "authoring_failed", "reason": f"worker crash: {e}"}
            results.append(r)
            print(f"[{i}/{len(targets)}] {r.get('status','?')} {pid} {r.get('reason','')[:120]}")

    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    report = {
        "generated_at": _now(),
        "targets": len(targets),
        "by_status": by_status,
        "workers": args.workers,
        "results": results,
    }
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps({"targets": len(targets), "by_status": by_status}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
