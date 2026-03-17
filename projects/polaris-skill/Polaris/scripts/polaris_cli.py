#!/usr/bin/env python3
"""Polaris CLI — single-command entry point for the Polaris orchestration skill.

Platform 2 APPROVED by Codex audit 2026-03-17.

Usage:
    polaris_cli.py run <command> [--goal GOAL] [--profile PROFILE] [--runtime-dir DIR] [--resume] [--shell-timeout-ms MS] [--no-prebuilt]
    polaris_cli.py stats --runtime-dir DIR [--json]
    polaris_cli.py experience reset-prebuilt --runtime-dir DIR [--ecosystem ECO]
    polaris_cli.py feedback reject <index> [--store PATH]
    polaris_cli.py feedback correct <index> --hint-kind KIND --hint-value JSON [--store PATH]
    polaris_cli.py feedback list [--store PATH]

Internally delegates to the same module path as polaris_runtime_demo.sh:
    compat check → bootstrap → orchestrator
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
PACKS_DIR = ROOT / "experience-packs"


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
    matching the given task fingerprint."""
    if not matching_key:
        return False
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


def _emit_experience_summary(state: dict, runtime_dir: Path, had_prior_experience: bool = False, global_experience_loaded: bool = False) -> None:
    """Emit human-readable experience summary lines to stderr (A2 + R1).

    Truthfulness contract: every line must reflect actual on-disk state.
    """
    artifacts = state.get("artifacts", {})
    lines = []

    hints = _safe_json_obj(artifacts.get("experience_hints"))
    avoid_count = len(hints.get("avoid", []))
    prefer_count = len(hints.get("prefer", []))
    # R5: Use experience_applied_count for truthful "actually applied" messages
    _applied_count_raw = artifacts.get("experience_applied_count", "0")
    try:
        _actual_applied = int(_applied_count_raw)
    except (ValueError, TypeError):
        _actual_applied = 0
    if _actual_applied > 0 and avoid_count > 0:
        source_note = " (includes global library)" if global_experience_loaded else ""
        lines.append(f"[polaris] \u21bb applied {_actual_applied} experience hints from previous failures{source_note}")
    elif avoid_count > 0 and _actual_applied == 0:
        # Hints were offered but all rejected by adapter (low confidence etc.)
        pass
    # Show reuse line only when experience wasn't actually applied —
    # otherwise the "succeeded on first try (experience hit: ...)" result line
    # already conveys reuse, making this line redundant noise.
    if prefer_count > 0 and _actual_applied == 0:
        _reuse_conf_str = ""
        try:
            sp_path = runtime_dir / "success-patterns.json"
            if sp_path.exists():
                sp_data = json.loads(sp_path.read_text())
                _sel_pat = artifacts.get("selected_pattern", "")
                for _pat in sp_data.get("patterns", []):
                    if _pat.get("pattern_id") == _sel_pat or _pat.get("fingerprint") == _sel_pat:
                        _conf = _pat.get("confidence", 0)
                        _rsc = _pat.get("reuse_success_count", 0)
                        if _rsc > 0:
                            _reuse_conf_str = f" from {_rsc} successful runs (confidence: {_conf/100:.2f})"
                        else:
                            _reuse_conf_str = f" (confidence: {_conf/100:.2f})"
                        break
        except (json.JSONDecodeError, OSError, TypeError):
            pass
        lines.append(f"[polaris] \u21bb reusing verified strategy{_reuse_conf_str}")
    # "no prior experience" is already conveyed by the result line
    # "succeeded (no prior experience for this task)" — don't duplicate.

    status = state.get("status")
    failure_written = artifacts.get("failure_record_written")
    if failure_written is True or failure_written == "true":
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
        # R5: experience actually applied but still failed
        if _actual_applied > 0:
            lines.append(f"[polaris] \u2717 failed despite experience hints (recording for improvement)")

    elif status == "completed":
        learning = _safe_json_obj(artifacts.get("learning_summary"))
        promoted = learning.get("promoted_patterns", [])
        merged = learning.get("merged_patterns", [])
        # Show "learned" only when there's genuinely new information for the user:
        # suppress when experience was already applied (the user is already reusing
        # this pattern — telling them it was "captured" again is noise).
        captured = (isinstance(promoted, list) and len(promoted) > 0) or \
                   (isinstance(merged, list) and len(merged) > 0)
        if captured and _actual_applied == 0:
            fp = _safe_json_obj(artifacts.get("task_fingerprint"))
            fp_key = fp.get("matching_key", "")[:12]
            adapter = artifacts.get("selected_adapter", "unknown")
            lines.append(f"[polaris] \u2713 learned: success pattern captured (fingerprint: {fp_key}, adapter: {adapter})")
        # R5: success + experience actually applied = first-try success message
        if _actual_applied > 0 and not artifacts.get("resumed_execution_contract"):
            # Find what error_class was avoided (from avoidance hints)
            avoided_classes = []
            for h in hints.get("avoid", []):
                ec = h.get("error_class")
                if ec and ec not in avoided_classes:
                    avoided_classes.append(ec)
            avoided_str = ", ".join(avoided_classes[:3]) if avoided_classes else "known failure patterns"
            lines.append(f"[polaris] \u2713 succeeded on first try (experience hit: avoided {avoided_str})")
        elif _actual_applied == 0 and prefer_count == 0 and status == "completed":
            lines.append(f"[polaris] \u2713 succeeded (no prior experience for this task)")

    for line in lines:
        print(line, file=sys.stderr)


# ── C1: Ecosystem detection and prebuilt pack loading ──

ECOSYSTEM_PATTERNS = {
    "node": re.compile(r"\b(npm|node|npx|yarn|pnpm)\b"),
    "python": re.compile(r"\b(python3?|pip3?|pytest|poetry|uv)\b"),
    "go": re.compile(r"\bgo\s"),
}


def _detect_ecosystem(command: str) -> str | None:
    """Detect ecosystem from command keywords."""
    for eco, pattern in ECOSYSTEM_PATTERNS.items():
        if pattern.search(command):
            return eco
    return None


def _load_prebuilt_pack(runtime_dir: Path, ecosystem: str) -> int:
    """Load a prebuilt experience pack into failure-records.json. Idempotent.
    Returns number of records added."""
    sys.path.insert(0, str(SCRIPTS))
    import polaris_failure_records as pfr

    pack_path = PACKS_DIR / f"{ecosystem}.json"
    if not pack_path.exists():
        return 0

    store_path = runtime_dir / "failure-records.json"
    store = pfr.load_store(store_path)

    # Idempotency: check if this ecosystem's prebuilt records already exist
    existing_prebuilt = [r for r in store.get("records", [])
                         if r.get("source") == "prebuilt" and r.get("ecosystem") == ecosystem]
    if existing_prebuilt:
        return 0

    pack = json.loads(pack_path.read_text())
    pack_records = pack.get("records", [])
    added = 0
    for prec in pack_records:
        # Each pack record becomes a failure record with source=prebuilt
        fp = {"matching_key": f"prebuilt-{ecosystem}-{added:04x}",
              "command_key": f"prebuilt-{ecosystem}",
              "raw_descriptor": prec.get("stderr_pattern", ""),
              "normalized_descriptor": prec.get("stderr_pattern", "")}
        entry = pfr.record(store, fp, f"prebuilt-{ecosystem}",
                           prec.get("error_class", "unknown"),
                           prec.get("description", ""),
                           "prebuilt",
                           prec.get("avoidance_hints", []),
                           source="prebuilt",
                           ecosystem=ecosystem)
        # R3: Store stderr_pattern for regex matching in query tier 3a
        if prec.get("stderr_pattern"):
            entry["stderr_pattern"] = prec["stderr_pattern"]
        added += 1

    pfr.write_store(store_path, store)
    return added


# ── D1: Event-log adapter events ──

def _write_event(runtime_dir: Path, event: dict) -> None:
    """Append an event to runtime-events.jsonl."""
    event.setdefault("ts", datetime.now(timezone.utc).isoformat())
    path = runtime_dir / "runtime-events.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, sort_keys=True) + "\n")


def cmd_run(args: argparse.Namespace) -> None:
    runtime_dir = Path(args.runtime_dir or _default_runtime_dir(args.command))
    runtime_dir.mkdir(parents=True, exist_ok=True)

    goal = args.goal or args.command
    profile = args.profile
    mode = "short" if profile in ("micro", "standard") else "long"

    # R1: Load global experience into runtime-dir before orchestrator
    import polaris_experience_store as pes
    global_dir, _ = pes.resolve_paths(runtime_dir)
    global_failure_path = global_dir / "failure-records.json"
    global_success_path = global_dir / "success-patterns.json"
    _global_experience_loaded = False
    try:
        if global_failure_path.exists():
            global_fstore, _ = pes.safe_load(global_failure_path)
            runtime_fstore_path = runtime_dir / "failure-records.json"
            runtime_fstore, _ = pes.safe_load(
                runtime_fstore_path,
                default_factory={"schema_version": 2, "records": []},
            )
            merged = pes.merge_failure_stores(runtime_fstore, global_fstore)
            pes.atomic_write(runtime_fstore_path, merged)
            _global_experience_loaded = True
        if global_success_path.exists():
            global_sstore, _ = pes.safe_load(
                global_success_path,
                default_factory={"schema_version": 1, "patterns": []},
            )
            runtime_sstore_path = runtime_dir / "success-patterns.json"
            runtime_sstore, _ = pes.safe_load(
                runtime_sstore_path,
                default_factory={"schema_version": 1, "patterns": []},
            )
            merged_s = pes.merge_success_stores(runtime_sstore, global_sstore)
            pes.atomic_write(runtime_sstore_path, merged_s)
            _global_experience_loaded = True
    except Exception as exc:
        print(f"[polaris] warning: global experience load failed ({exc}), continuing without", file=sys.stderr)

    # 1. Compat gates
    _run([sys.executable, str(SCRIPTS / "polaris_compat.py"), "check-runtime-format", "--runtime-dir", str(runtime_dir)], "compat: check-runtime-format")
    _run([sys.executable, str(SCRIPTS / "polaris_compat.py"), "check-schema", "--state", str(runtime_dir / "execution-state.json")], "compat: check-schema")
    _run([sys.executable, str(SCRIPTS / "polaris_compat.py"), "write-runtime-format", "--runtime-dir", str(runtime_dir)], "compat: write-runtime-format")

    # 2. Bootstrap
    _run([sys.executable, str(SCRIPTS / "polaris_bootstrap.py"), "bootstrap", "--manifest", str(SCRIPTS / "polaris_bootstrap.json"), "--runtime-dir", str(runtime_dir)], "bootstrap")

    # C1: Load prebuilt experience pack if applicable
    no_prebuilt = getattr(args, "no_prebuilt", False) or os.environ.get("POLARIS_NO_PREBUILT") == "1"
    if not no_prebuilt:
        eco = _detect_ecosystem(args.command)
        if eco:
            _load_prebuilt_pack(runtime_dir, eco)

    # R2: Resolve shell cwd (user-provided or default to runtime-dir)
    shell_cwd = getattr(args, "cwd", None) or str(runtime_dir)

    # Compute task fingerprint and snapshot per-task experience BEFORE orchestrator runs
    sys.path.insert(0, str(SCRIPTS))
    import polaris_task_fingerprint as ptf
    task_fp = ptf.compute(args.command, shell_cwd)
    task_matching_key = task_fp.get("matching_key", "")
    had_prior_experience = _has_prior_experience_for_task(runtime_dir, task_matching_key)

    # D1: Emit adapter_selected event after orchestrator selects adapter
    # (We capture timing for adapter_outcome)
    exec_start = time.monotonic()

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
    if shell_cwd != str(runtime_dir):
        orch_args.extend(["--shell-cwd", shell_cwd])
    if args.resume:
        orch_args.append("--resume")
    if args.shell_timeout_ms:
        orch_args.extend(["--shell-timeout-ms", str(args.shell_timeout_ms)])

    result = subprocess.run(orch_args, capture_output=True, text=True)
    exec_end = time.monotonic()
    duration_ms = int((exec_end - exec_start) * 1000)

    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)

    # D1: Read state and emit adapter events to event-log
    state_path = runtime_dir / "execution-state.json"
    if state_path.exists():
        state = json.loads(state_path.read_text())
        artifacts = state.get("artifacts", {})
        adapter_name = artifacts.get("selected_adapter", "unknown")
        status = state.get("status", "unknown")

        # Parse orchestrator stdout for selection_trace info
        orch_parsed = {}
        try:
            orch_parsed = json.loads(result.stdout.strip()) if result.stdout.strip() else {}
        except (json.JSONDecodeError, ValueError):
            pass
        selection_trace = orch_parsed.get("selected_adapter", {}).get("selection_trace", {})
        scenario_fp = selection_trace.get("scenario_fingerprint", "")
        sticky_reuse = selection_trace.get("sticky_reuse", {})
        cache_hit = bool(sticky_reuse.get("entry"))

        # Determine score from selected adapter
        selected_list = orch_parsed.get("selected_adapter", {}).get("selected", [])
        adapter_score = selected_list[0].get("score", 0) if selected_list else 0

        # adapter_selected event
        _write_event(runtime_dir, {
            "type": "adapter_selected",
            "adapter": adapter_name,
            "score": adapter_score,
            "scenario_fingerprint": scenario_fp,
            "cache_hit": cache_hit,
        })

        # adapter_outcome event
        success = status == "completed"
        exit_code = 0 if success else (result.returncode or 1)
        error_class = artifacts.get("error_class", "") if not success else ""
        _write_event(runtime_dir, {
            "type": "adapter_outcome",
            "adapter": adapter_name,
            "success": success,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "error_class": error_class,
        })

        # R5: experience_hit event — use experience_applied_count from adapter output
        # (not experience_hints existence, which includes rejected low-confidence hints)
        _applied_count_raw = artifacts.get("experience_applied_count", "0")
        try:
            _applied_count = int(_applied_count_raw)
        except (ValueError, TypeError):
            _applied_count = 0
        experience_actually_applied = _applied_count > 0
        # direct_hit: experience actually applied AND first-try success (no repair branch)
        repaired = bool(artifacts.get("resumed_execution_contract"))
        direct_hit = experience_actually_applied and success and not repaired
        # repair_rounds: 0 if clean success, 1 if repair branch was entered
        repair_rounds = 1 if repaired else 0
        if experience_actually_applied:
            _write_event(runtime_dir, {
                "type": "experience_hit",
                "hit": True,
                "direct_hit": direct_hit,
                "success": success,
                "applied_count": _applied_count,
                "repair_rounds": repair_rounds,
                "task_matching_key": task_matching_key,
                "command": args.command,
            })
        # Also emit experience_query event for every run (hit or miss)
        _write_event(runtime_dir, {
            "type": "experience_query",
            "had_experience": experience_actually_applied,
            "success": success,
            "repair_rounds": repair_rounds,
            "task_matching_key": task_matching_key,
        })

        # R1: Sync runtime experience back to global library
        try:
            runtime_fstore, _ = pes.safe_load(
                runtime_dir / "failure-records.json",
                default_factory={"schema_version": 2, "records": []},
            )
            pes.sync_failure_to_global(runtime_fstore, global_failure_path)
            runtime_sstore, _ = pes.safe_load(
                runtime_dir / "success-patterns.json",
                default_factory={"schema_version": 1, "patterns": []},
            )
            pes.sync_success_to_global(runtime_sstore, global_success_path)
        except Exception as exc:
            print(f"[polaris] warning: global experience sync failed ({exc})", file=sys.stderr)

        _emit_experience_summary(state, runtime_dir, had_prior_experience, global_experience_loaded=_global_experience_loaded)

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
    """Parse runtime-events.jsonl for run statistics, adapter performance, and experience metrics."""
    result = {
        "total_runs": 0,
        "total_queries": 0,
        "total_hits": 0,
        "direct_hits": 0,
        "experience_hit_events": 0,
        "task_hits": {},
        "adapter_stats": {},
        "adapter_selections": 0,
        "adapter_cache_hits": 0,
        # R5: repair efficiency tracking
        "repair_rounds_with_experience": [],
        "repair_rounds_without_experience": [],
    }
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
            etype = event.get("type")

            if etype == "adapter_selected":
                result["adapter_selections"] += 1
                if event.get("cache_hit"):
                    result["adapter_cache_hits"] += 1

            elif etype == "adapter_outcome":
                adapter = event.get("adapter", "unknown")
                if adapter not in result["adapter_stats"]:
                    result["adapter_stats"][adapter] = {
                        "calls": 0, "successes": 0, "total_duration_ms": 0
                    }
                stats = result["adapter_stats"][adapter]
                stats["calls"] += 1
                if event.get("success"):
                    stats["successes"] += 1
                stats["total_duration_ms"] += event.get("duration_ms", 0)

            elif etype == "experience_hit":
                result["experience_hit_events"] += 1
                result["total_hits"] += 1
                if event.get("direct_hit"):
                    result["direct_hits"] += 1
                task_key = event.get("task_matching_key", "")
                cmd = event.get("command", "unknown")
                if task_key not in result["task_hits"]:
                    result["task_hits"][task_key] = {"command": cmd, "hits": 0, "direct_hits": 0}
                result["task_hits"][task_key]["hits"] += 1
                if event.get("direct_hit"):
                    result["task_hits"][task_key]["direct_hits"] += 1

            elif etype == "experience_query":
                result["total_queries"] += 1
                repair_rounds = int(event.get("repair_rounds", 0))
                if event.get("had_experience"):
                    result["repair_rounds_with_experience"].append(repair_rounds)
                else:
                    result["repair_rounds_without_experience"].append(repair_rounds)

            elif event.get("status") == "completed":
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

    # R5: Compute repair efficiency metrics
    rr_with = event_stats["repair_rounds_with_experience"]
    rr_without = event_stats["repair_rounds_without_experience"]
    avg_repair_with = (sum(rr_with) / len(rr_with)) if rr_with else 0.0
    avg_repair_without = (sum(rr_without) / len(rr_without)) if rr_without else 0.0
    # tokens_saved estimate: each avoided repair round ≈ 1 LLM call saved
    repair_cycles_avoided = max(0, int((avg_repair_without - avg_repair_with) * len(rr_with)))

    # R5: Top experienced tasks (sorted by hits descending)
    top_tasks = sorted(
        event_stats["task_hits"].values(),
        key=lambda t: (-t["hits"], -t["direct_hits"]),
    )[:10]

    return {
        "failure_records": len(failures),
        "failure_by_error_class": error_classes,
        "failure_oldest": min(failure_dates) if failure_dates else None,
        "failure_newest": max(failure_dates) if failure_dates else None,
        "success_patterns": len(patterns),
        "patterns_by_lifecycle": lifecycle_states,
        "patterns_by_adapter": adapters,
        "total_runs": event_stats["total_runs"],
        "adapter_stats": event_stats["adapter_stats"],
        "adapter_selections": event_stats["adapter_selections"],
        "adapter_cache_hits": event_stats["adapter_cache_hits"],
        # R5: experience observability
        "hits": event_stats["total_hits"],
        "direct_hits": event_stats["direct_hits"],
        "experience_queries": event_stats["total_queries"],
        "experience_hit_events": event_stats["experience_hit_events"],
        "repair_rounds_avg_with_experience": round(avg_repair_with, 2),
        "repair_rounds_avg_without_experience": round(avg_repair_without, 2),
        "tokens_saved": {"estimate": True, "repair_cycles_avoided": repair_cycles_avoided},
        "top_tasks": top_tasks,
    }


def cmd_stats(args: argparse.Namespace) -> None:
    """Show experience store summary (A3 + D1)."""
    stats = _build_stats(Path(args.runtime_dir))

    has_data = stats["failure_records"] > 0 or stats["success_patterns"] > 0 or stats["total_runs"] > 0

    if args.json_output:
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

        # R5: Experience Hits section
        queries = stats.get("experience_queries", 0)
        hits = stats.get("hits", 0)
        direct_hits = stats.get("direct_hits", 0)
        if queries > 0:
            hit_pct = (hits / queries * 100) if queries > 0 else 0.0
            print(f"Experience Hits:  {queries} queries \u2192 {hits} hits ({hit_pct:.1f}%)")
            print(f"  Direct hits (first-try success): {direct_hits}")
            error_avoidance = hits - direct_hits
            print(f"  Error avoidance hits:            {error_avoidance}")

        # R5: Repair Efficiency section
        avg_with = stats.get("repair_rounds_avg_with_experience", 0.0)
        avg_without = stats.get("repair_rounds_avg_without_experience", 0.0)
        tokens_saved = stats.get("tokens_saved", {})
        cycles_avoided = tokens_saved.get("repair_cycles_avoided", 0)
        if avg_with > 0 or avg_without > 0:
            print("Repair Efficiency:")
            print(f"  With experience:    avg {avg_with:.1f} repair rounds")
            print(f"  Without experience: avg {avg_without:.1f} repair rounds")
            print(f"  Estimated savings:  ~{cycles_avoided} repair cycles avoided")

        # R5: Top Experienced Tasks
        top_tasks = stats.get("top_tasks", [])
        if top_tasks:
            print()
            print("Top Experienced Tasks:")
            for i, t in enumerate(top_tasks[:5], 1):
                cmd = t.get("command", "unknown")
                # Truncate long commands
                if len(cmd) > 40:
                    cmd = cmd[:37] + "..."
                print(f"  {i}. {cmd:<40s} \u2014 {t['hits']} hits, {t['direct_hits']} direct successes")

        # D1: Adapter Performance section
        adapter_stats = stats.get("adapter_stats", {})
        if adapter_stats:
            print()
            print("Adapter Performance")
            print("===================")
            for name, st in sorted(adapter_stats.items()):
                calls = st["calls"]
                successes = st["successes"]
                rate = (successes / calls * 100) if calls > 0 else 0.0
                avg_ms = (st["total_duration_ms"] / calls / 1000) if calls > 0 else 0.0
                print(f"{name}:  {calls} calls, {successes} success ({rate:.1f}%), avg {avg_ms:.1f}s")
            sels = stats["adapter_selections"]
            cache_hits = stats["adapter_cache_hits"]
            hit_rate = (cache_hits / sels * 100) if sels > 0 else 0.0
            print(f"Cache hit rate: {hit_rate:.1f}% (out of {sels} selections)")


def cmd_experience_reset_prebuilt(args: argparse.Namespace) -> None:
    """Remove all prebuilt experience records (C1)."""
    sys.path.insert(0, str(SCRIPTS))
    import polaris_failure_records as pfr

    store_path = Path(args.runtime_dir) / "failure-records.json"
    store = pfr.load_store(store_path)
    removed = pfr.reset_prebuilt(store, ecosystem=args.ecosystem)
    pfr.write_store(store_path, store)
    print(f"Removed {removed} prebuilt records")


def cmd_feedback_reject(args: argparse.Namespace) -> None:
    """Mark a failure record as rejected (C2)."""
    sys.path.insert(0, str(SCRIPTS))
    import polaris_failure_records as pfr

    store_path = Path(args.store)
    store = pfr.load_store(store_path)
    ok = pfr.reject_record(store, args.index)
    if not ok:
        print(f"Error: index {args.index} out of range", file=sys.stderr)
        sys.exit(1)
    pfr.write_store(store_path, store)
    print(f"Record {args.index} rejected")


def cmd_feedback_correct(args: argparse.Namespace) -> None:
    """Create a user correction for a failure record (C2)."""
    sys.path.insert(0, str(SCRIPTS))
    import polaris_failure_records as pfr

    if args.hint_kind not in pfr.HINT_KINDS:
        print(f"Error: invalid hint kind '{args.hint_kind}', must be one of: {', '.join(sorted(pfr.HINT_KINDS))}", file=sys.stderr)
        sys.exit(1)

    store_path = Path(args.store)
    store = pfr.load_store(store_path)
    try:
        hint_value = json.loads(args.hint_value)
    except json.JSONDecodeError:
        print("Error: --hint-value must be valid JSON", file=sys.stderr)
        sys.exit(1)
    entry = pfr.correct_record(store, args.index, args.hint_kind, hint_value)
    if entry is None:
        print(f"Error: index {args.index} out of range or invalid hint kind", file=sys.stderr)
        sys.exit(1)
    pfr.write_store(store_path, store)
    print(json.dumps(entry, sort_keys=True))


def cmd_feedback_list(args: argparse.Namespace) -> None:
    """List all rejected and user_correction records (C2)."""
    sys.path.insert(0, str(SCRIPTS))
    import polaris_failure_records as pfr

    store_path = Path(args.store)
    store = pfr.load_store(store_path)
    items = pfr.list_feedback(store)
    if not items:
        print("No feedback records found")
    else:
        for item in items:
            status = "rejected" if item.get("rejected_by") else item.get("source", "")
            print(f"[{item['index']}] {status}: {item['command']} ({item['error_class']})")


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
    run_parser.add_argument("--cwd", default=None, help="Working directory for the command (default: runtime-dir)")
    run_parser.add_argument("--no-prebuilt", action="store_true", default=False, help="Do not load prebuilt experience packs")

    # --- stats ---
    stats_parser = subparsers.add_parser("stats", help="Show experience store summary")
    stats_parser.add_argument("--runtime-dir", required=True, help="Runtime directory to inspect")
    stats_parser.add_argument("--json", dest="json_output", action="store_true", default=False, help="Output as JSON")

    # --- experience ---
    exp_parser = subparsers.add_parser("experience", help="Manage experience store")
    exp_sub = exp_parser.add_subparsers(dest="exp_command")
    reset_parser = exp_sub.add_parser("reset-prebuilt", help="Remove prebuilt experience records")
    reset_parser.add_argument("--runtime-dir", required=True, help="Runtime directory")
    reset_parser.add_argument("--ecosystem", default=None, choices=["node", "python", "go"], help="Only reset this ecosystem")

    # --- feedback ---
    fb_parser = subparsers.add_parser("feedback", help="User feedback on experience records")
    fb_sub = fb_parser.add_subparsers(dest="fb_command")

    rej_parser = fb_sub.add_parser("reject", help="Reject a failure record")
    rej_parser.add_argument("index", type=int, help="Record index to reject")
    rej_parser.add_argument("--store", required=True, help="Path to failure-records.json")

    cor_parser = fb_sub.add_parser("correct", help="Correct a failure record")
    cor_parser.add_argument("index", type=int, help="Record index to correct")
    cor_parser.add_argument("--hint-kind", required=True, help="Hint kind (set_env, append_flags, rewrite_cwd, set_timeout)")
    cor_parser.add_argument("--hint-value", required=True, help="Hint value as JSON")
    cor_parser.add_argument("--store", required=True, help="Path to failure-records.json")

    list_parser = fb_sub.add_parser("list", help="List feedback records")
    list_parser.add_argument("--store", required=True, help="Path to failure-records.json")

    args = parser.parse_args()

    if args.subcommand is None:
        parser.print_help()
        sys.exit(2)
    elif args.subcommand == "run":
        cmd_run(args)
    elif args.subcommand == "stats":
        cmd_stats(args)
    elif args.subcommand == "experience":
        if args.exp_command == "reset-prebuilt":
            cmd_experience_reset_prebuilt(args)
        else:
            exp_parser.print_help()
            sys.exit(2)
    elif args.subcommand == "feedback":
        if args.fb_command == "reject":
            cmd_feedback_reject(args)
        elif args.fb_command == "correct":
            cmd_feedback_correct(args)
        elif args.fb_command == "list":
            cmd_feedback_list(args)
        else:
            fb_parser.print_help()
            sys.exit(2)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()
