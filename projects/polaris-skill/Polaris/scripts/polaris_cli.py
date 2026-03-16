#!/usr/bin/env python3
"""Polaris CLI — single-command entry point for the Polaris orchestration skill.

Usage:
    polaris_cli.py run <command> [--goal GOAL] [--profile PROFILE] [--runtime-dir DIR] [--resume] [--shell-timeout-ms MS]
    polaris_cli.py experience reset-prebuilt [--runtime-dir DIR] [--ecosystem ECO]
    polaris_cli.py feedback reject <index> [--store PATH]
    polaris_cli.py feedback correct <index> --hint-kind KIND --hint-value JSON [--store PATH]
    polaris_cli.py feedback list [--store PATH]

Internally delegates to the same module path as polaris_runtime_demo.sh:
    compat check → bootstrap → orchestrator
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent


def _default_runtime_dir(command: str) -> str:
    h = hashlib.sha256(command.encode()).hexdigest()[:12]
    return f"/tmp/polaris-{h}"


def _run(cmd: list[str], label: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    if check and result.returncode != 0:
        raise SystemExit(f"[polaris] {label} failed (exit {result.returncode})")
    return result


def _safe_json_list(raw) -> list[dict]:
    """Parse a raw artifact value into a list of dicts, safely."""
    if raw is None:
        return []
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _safe_json_obj(raw) -> dict:
    """Parse a raw artifact value into a dict, safely."""
    if raw is None:
        return {}
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _has_prior_experience_for_task(runtime_dir: Path, matching_key: str) -> bool:
    """Check failure-records.json and success-patterns.json for experience
    matching the given task fingerprint.

    Only returns True if the specific task (by matching_key) has prior records,
    not just any task in the same runtime directory.
    """
    if not matching_key:
        return False
    # Failure records: check for matching_key
    fr_path = runtime_dir / "failure-records.json"
    if fr_path.exists():
        try:
            data = json.loads(fr_path.read_text())
            items = data.get("records", [])
            if isinstance(items, list):
                for rec in items:
                    if isinstance(rec, dict):
                        rec_key = rec.get("task_fingerprint", {}).get("matching_key", "")
                        if rec_key == matching_key:
                            return True
        except (json.JSONDecodeError, OSError):
            pass
    # Success patterns: check for matching_key in task_fingerprint
    sp_path = runtime_dir / "success-patterns.json"
    if sp_path.exists():
        try:
            data = json.loads(sp_path.read_text())
            items = data.get("patterns", [])
            if isinstance(items, list):
                for pat in items:
                    if isinstance(pat, dict):
                        fp = pat.get("task_fingerprint")
                        if isinstance(fp, dict) and fp.get("matching_key") == matching_key:
                            return True
        except (json.JSONDecodeError, OSError):
            pass
    return False


def _emit_experience_summary(state: dict, runtime_dir: Path, had_prior_experience: bool = False) -> None:
    """Emit human-readable experience summary lines to stderr (A2).

    Truthfulness contract: every line must reflect actual on-disk state.
    - "applied N avoidance hints" → experience_hints.avoid has N entries
    - "applied N strategy hints" → experience_hints.prefer has N entries
    - "first run for this task" → no records for this task's fingerprint existed before run
    - "learned: ... stored" → failure record is on-disk in failure-records.json
    - "learned: success pattern captured" → pattern was promoted or merged (on-disk)
    """
    artifacts = state.get("artifacts", {})
    lines = []

    # 1. Experience hints applied? Separate avoid (from failures) and prefer (from patterns)
    hints = _safe_json_obj(artifacts.get("experience_hints"))
    avoid_count = len(hints.get("avoid", []))
    prefer_count = len(hints.get("prefer", []))
    if avoid_count > 0:
        lines.append(f"[polaris] \u21bb applied {avoid_count} avoidance hints from previous failures")
    if prefer_count > 0:
        lines.append(f"[polaris] \u21bb applied {prefer_count} strategy hints from success patterns")
    if avoid_count == 0 and prefer_count == 0 and not had_prior_experience:
        lines.append("[polaris] first run for this task, no prior experience")

    # 2. What was learned this run?
    status = state.get("status")
    failure_written = artifacts.get("failure_record_written")
    if failure_written is True or failure_written == "true":
        # Extract error class and hint kinds from on-disk failure records
        fp = _safe_json_obj(artifacts.get("task_fingerprint"))
        matching_key = fp.get("matching_key", "")
        error_class = "unknown"
        hint_kinds: list[str] = []
        failure_store_path = runtime_dir / "failure-records.json"
        if matching_key and failure_store_path.exists():
            try:
                store = json.loads(failure_store_path.read_text())
                records = store.get("records", [])
                if isinstance(records, list):
                    for rec in reversed(records):
                        if not isinstance(rec, dict):
                            continue
                        rec_key = rec.get("task_fingerprint", {}).get("matching_key", "")
                        if rec_key == matching_key:
                            error_class = rec.get("error_class", "unknown")
                            hint_kinds = [h.get("kind", "?") for h in rec.get("avoidance_hints", []) if isinstance(h, dict)]
                            break
            except (json.JSONDecodeError, OSError):
                pass
        hint_kinds_str = ", ".join(hint_kinds) if hint_kinds else "general"
        lines.append(f"[polaris] \u2717 learned: {error_class} \u2192 avoidance hints [{hint_kinds_str}] stored for next run")

    elif status == "completed":
        # Fix #2: check promoted_patterns + merged_patterns as on-disk evidence,
        # not success_markers which is just a queue count
        learning = _safe_json_obj(artifacts.get("learning_summary"))
        promoted = learning.get("promoted_patterns", [])
        merged = learning.get("merged_patterns", [])
        captured = (isinstance(promoted, list) and len(promoted) > 0) or \
                   (isinstance(merged, list) and len(merged) > 0)
        if captured:
            fp = _safe_json_obj(artifacts.get("task_fingerprint"))
            fp_key = fp.get("matching_key", "")[:12]
            adapter = artifacts.get("selected_adapter", "unknown")
            lines.append(f"[polaris] \u2713 learned: success pattern captured (fingerprint: {fp_key}, adapter: {adapter})")

    for line in lines:
        print(line, file=sys.stderr)


def cmd_run(args: argparse.Namespace) -> None:
    runtime_dir = Path(args.runtime_dir or _default_runtime_dir(args.command))
    runtime_dir.mkdir(parents=True, exist_ok=True)

    goal = args.goal or args.command
    profile = args.profile
    mode = "short" if profile in ("micro", "standard") else "long"

    # 1. Compat gates (same as polaris_runtime_demo.sh)
    _run([sys.executable, str(SCRIPTS / "polaris_compat.py"), "check-runtime-format", "--runtime-dir", str(runtime_dir)], "compat: check-runtime-format")
    _run([sys.executable, str(SCRIPTS / "polaris_compat.py"), "check-schema", "--state", str(runtime_dir / "execution-state.json")], "compat: check-schema")
    _run([sys.executable, str(SCRIPTS / "polaris_compat.py"), "write-runtime-format", "--runtime-dir", str(runtime_dir)], "compat: write-runtime-format")

    # 2. Bootstrap (idempotent)
    _run([sys.executable, str(SCRIPTS / "polaris_bootstrap.py"), "bootstrap", "--manifest", str(SCRIPTS / "polaris_bootstrap.json"), "--runtime-dir", str(runtime_dir)], "bootstrap")

    # Compute task fingerprint and snapshot per-task experience BEFORE orchestrator runs
    sys.path.insert(0, str(SCRIPTS))
    import polaris_task_fingerprint as ptf
    task_fp = ptf.compute(args.command, str(runtime_dir))
    task_matching_key = task_fp.get("matching_key", "")
    had_prior_experience = _has_prior_experience_for_task(runtime_dir, task_matching_key)

    # 3. Orchestrator
    orch_args = [
        sys.executable, str(SCRIPTS / "polaris_orchestrator.py"),
        "--state", str(runtime_dir / "execution-state.json"),
        "--goal", goal,
        "--adapters", str(runtime_dir / "adapters.json"),
        "--rules", str(runtime_dir / "rules.json"),
        "--patterns", str(runtime_dir / "success-patterns.json"),
        "--mode", mode,
        "--execution-profile", profile,
        "--execution-kind", "shell_command",
        "--shell-command", args.command,
    ]
    if args.resume:
        orch_args.append("--resume")
    if args.shell_timeout_ms:
        orch_args.extend(["--shell-timeout-ms", str(args.shell_timeout_ms)])

    result = subprocess.run(orch_args, capture_output=True, text=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)

    # Determine exit code and emit experience summary
    state_path = runtime_dir / "execution-state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        _emit_experience_summary(state, runtime_dir, had_prior_experience)
        status = state.get("status")
        if status == "completed":
            sys.exit(0)
        elif status == "blocked":
            sys.exit(1)
        else:
            sys.exit(result.returncode or 1)
    else:
        sys.exit(result.returncode or 1)


def _load_safe_list(path: Path, key: str) -> list[dict]:
    """Load a JSON file and extract a list of dicts from the given key, with type guards."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        items = data.get(key, [])
        if not isinstance(items, list):
            print(f"[polaris] warning: {path.name} .{key} is not a list, treating as empty", file=sys.stderr)
            return []
        return [item for item in items if isinstance(item, dict)]
    except (json.JSONDecodeError, OSError, AttributeError):
        print(f"[polaris] warning: {path.name} is corrupt or unreadable, treating as empty", file=sys.stderr)
        return []


def _parse_event_log(path: Path) -> dict:
    """Parse runtime-events.jsonl for run statistics.

    The event log is a state journal written by polaris_report.py /
    polaris_runtime.py.  Each line is a JSON object with fields like
    ``phase``, ``status``, ``summary``, ``ts``.  A completed run is
    indicated by ``status == "completed"``.

    Experience-query events (experience_queries / experience_hits) are
    not yet emitted by the orchestrator — those fields are reserved for
    Phase D and always report 0 for now.
    """
    result = {"total_runs": 0, "total_queries": 0, "total_hits": 0, "task_hits": {}}
    if not path.exists():
        return result
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("status") == "completed":
                result["total_runs"] += 1
    except OSError:
        pass
    return result


def _build_stats(runtime_dir: Path) -> dict:
    """Build the unified stats object from all experience files."""
    failures = _load_safe_list(runtime_dir / "failure-records.json", "records")
    patterns = _load_safe_list(runtime_dir / "success-patterns.json", "patterns")
    event_stats = _parse_event_log(runtime_dir / "runtime-events.jsonl")

    error_classes: dict[str, int] = {}
    failure_dates: list[str] = []
    for rec in failures:
        ec = rec.get("error_class") or "unknown"
        error_classes[ec] = error_classes.get(ec, 0) + 1
        ts = rec.get("recorded_at", "")
        if isinstance(ts, str) and len(ts) >= 10:
            failure_dates.append(ts[:10])

    lifecycle_states: dict[str, int] = {}
    adapters: dict[str, int] = {}
    for pat in patterns:
        ls = pat.get("lifecycle_state") or "unknown"
        lifecycle_states[ls] = lifecycle_states.get(ls, 0) + 1
        ad = pat.get("adapter") or "unknown"
        adapters[ad] = adapters.get(ad, 0) + 1

    return {
        "failure_records": len(failures),
        "failure_by_error_class": error_classes,
        "failure_oldest": min(failure_dates) if failure_dates else None,
        "failure_newest": max(failure_dates) if failure_dates else None,
        "success_patterns": len(patterns),
        "patterns_by_lifecycle": lifecycle_states,
        "patterns_by_adapter": adapters,
        "total_runs": event_stats["total_runs"],
    }


def cmd_stats(args: argparse.Namespace) -> None:
    """Show experience store summary (A3)."""
    stats = _build_stats(Path(args.runtime_dir))

    has_data = stats["failure_records"] > 0 or stats["success_patterns"] > 0 or stats["total_runs"] > 0

    if args.json_output:
        # Fix #5: stable schema — always output all fields
        print(json.dumps(stats, indent=2, sort_keys=True))
    elif not has_data:
        print("no experience recorded yet")
    else:
        ec_parts = ", ".join(f"{c} {k}" for k, c in sorted(stats["failure_by_error_class"].items(), key=lambda x: -x[1]))
        lc_parts = ", ".join(f"{c} {k}" for k, c in sorted(stats["patterns_by_lifecycle"].items(), key=lambda x: -x[1]))
        ad_parts = ", ".join(f"{k}: {c}" for k, c in sorted(stats["patterns_by_adapter"].items(), key=lambda x: -x[1]))

        print("Experience Store Summary")
        print("========================")
        print(f"Failure Records:  {stats['failure_records']} total ({ec_parts})" if stats["failure_records"] else "Failure Records:  0")
        if stats["failure_oldest"]:
            print(f"  Oldest: {stats['failure_oldest']}  Newest: {stats['failure_newest']}")
        print(f"Success Patterns: {stats['success_patterns']} total ({lc_parts})" if stats["success_patterns"] else "Success Patterns: 0")
        if stats["patterns_by_adapter"]:
            print(f"  By adapter: {ad_parts}")
        tr = stats["total_runs"]
        print(f"Runs:             {tr} completed" if tr > 0 else "Runs:             0")


def main() -> None:
    parser = argparse.ArgumentParser(prog="polaris", description="Polaris orchestration CLI")
    subparsers = parser.add_subparsers(dest="subcommand")

    # --- run ---
    run_parser = subparsers.add_parser("run", help="Execute a command through Polaris orchestration")
    run_parser.add_argument("command", help="Shell command to execute")
    run_parser.add_argument("--goal", help="Human-readable goal description (defaults to command)")
    run_parser.add_argument("--profile", choices=["micro", "standard", "deep"], default="micro", help="Execution profile")
    run_parser.add_argument("--runtime-dir", help="Runtime directory (default: /tmp/polaris-<hash>)")
    run_parser.add_argument("--resume", action="store_true", default=False, help="Resume from blocked state")
    run_parser.add_argument("--shell-timeout-ms", type=int, default=60000, help="Shell command timeout in ms")

    # --- stats ---
    stats_parser = subparsers.add_parser("stats", help="Show experience store summary")
    stats_parser.add_argument("--runtime-dir", required=True, help="Runtime directory to inspect")
    stats_parser.add_argument("--json", dest="json_output", action="store_true", default=False, help="Output as JSON")

    args = parser.parse_args()

    if args.subcommand is None:
        parser.print_help()
        sys.exit(2)
    elif args.subcommand == "run":
        cmd_run(args)
    elif args.subcommand == "stats":
        cmd_stats(args)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
