#!/usr/bin/env python3
"""Bootstrap protocol: reads a manifest, validates host requirements, registers assets idempotently."""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_adapter(record: dict) -> dict:
    """Normalize an adapter record to a comparable form (drop updated_at)."""
    mode_preferences = record.get("mode_preferences", {})
    if isinstance(mode_preferences, str):
        mp = {}
        for item in parse_csv(mode_preferences):
            key, _, value = item.partition(":")
            if key and value:
                mp[key] = int(value)
        mode_preferences = mp
    return {
        "tool": record.get("tool"),
        "command": record.get("command"),
        "inputs": parse_csv(record["inputs"]) if isinstance(record.get("inputs"), str) else record.get("inputs", []),
        "capabilities": parse_csv(record["capabilities"]) if isinstance(record.get("capabilities"), str) else record.get("capabilities", []),
        "modes": parse_csv(record["modes"]) if isinstance(record.get("modes"), str) else record.get("modes", []),
        "prerequisites": parse_csv(record["prerequisites"]) if isinstance(record.get("prerequisites"), str) else record.get("prerequisites", []),
        "selectors": parse_csv(record["selectors"]) if isinstance(record.get("selectors"), str) else record.get("selectors", []),
        "failure_notes": parse_csv(record["failure_notes"]) if isinstance(record.get("failure_notes"), str) else record.get("failure_notes", []),
        "fallbacks": parse_csv(record.get("fallbacks", "")) if isinstance(record.get("fallbacks"), str) else record.get("fallbacks", []),
        "fallback_notes": parse_csv(record.get("fallback_notes", "")) if isinstance(record.get("fallback_notes"), str) else record.get("fallback_notes", []),
        "mode_preferences": mode_preferences,
        "trust_level": record.get("trust_level", "workspace"),
        "cost_hint": record.get("cost_hint", 1),
        "latency_hint": record.get("latency_hint", 1),
        "preferred_failures": parse_csv(record["preferred_failures"]) if isinstance(record.get("preferred_failures"), str) else record.get("preferred_failures", []),
        "avoid_failures": parse_csv(record.get("avoid_failures", "")) if isinstance(record.get("avoid_failures"), str) else record.get("avoid_failures", []),
        "safe_retry": record.get("safe_retry") if isinstance(record.get("safe_retry"), bool) else record.get("safe_retry") == "yes",
        "notes": record.get("notes", ""),
    }


def normalize_rule(record: dict) -> dict:
    """Normalize a rule record to a comparable form."""
    return {
        "rule_id": record.get("rule_id"),
        "layer": record.get("layer"),
        "trigger": record.get("trigger"),
        "action": record.get("action"),
        "evidence": record.get("evidence"),
        "scope": record.get("scope"),
        "tags": parse_csv(record["tags"]) if isinstance(record.get("tags"), str) else record.get("tags", []),
        "validation": record.get("validation", "observed local evidence"),
        "priority": record.get("priority", 50),
        "asset_version": record.get("asset_version", 2),
    }


def normalize_pattern(record: dict) -> dict:
    """Normalize a pattern record to a comparable form."""
    return {
        "pattern_id": record.get("pattern_id"),
        "summary": record.get("summary"),
        "trigger": record.get("trigger"),
        "sequence": parse_csv(record["sequence"]) if isinstance(record.get("sequence"), str) else record.get("sequence", []),
        "outcome": record.get("outcome"),
        "evidence": parse_csv(record["evidence"]) if isinstance(record.get("evidence"), str) else record.get("evidence", []),
        "tags": parse_csv(record["tags"]) if isinstance(record.get("tags"), str) else record.get("tags", []),
        "modes": parse_csv(record["modes"]) if isinstance(record.get("modes"), str) else record.get("modes", []),
        "confidence": record.get("confidence", 60),
        "lifecycle_state": record.get("lifecycle_state", "experimental"),
    }


KNOWN_CAPABILITIES = {
    "local-exec": "interpreter can execute a trivial script",
    "reporting": "runtime dir is writable",
}


def check_requires(requires: dict, runtime_dir: Path) -> dict:
    """Validate manifest requires against the actual host environment."""
    results = {}

    # interpreter check
    interpreter = requires.get("interpreter")
    if interpreter:
        path = shutil.which(interpreter)
        if path is None:
            results["interpreter"] = {"status": "fail", "reason": f"{interpreter} not found on PATH"}
            return results
        results["interpreter"] = {"status": "pass", "path": path}

    # capabilities check — probe the host, not just manifest consistency
    for cap in requires.get("capabilities", []):
        if cap not in KNOWN_CAPABILITIES:
            results[f"capability:{cap}"] = {"status": "fail", "reason": f"unsupported capability: {cap}"}
            return results
        if cap == "local-exec":
            interp = requires.get("interpreter", "python3")
            try:
                result = subprocess.run(
                    [interp, "-c", "print('ok')"],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    results[f"capability:{cap}"] = {"status": "pass", "probe": "trivial script executed"}
                else:
                    results[f"capability:{cap}"] = {"status": "fail", "reason": f"trivial script failed: {result.stderr.strip()}"}
                    return results
            except (FileNotFoundError, subprocess.TimeoutExpired) as e:
                results[f"capability:{cap}"] = {"status": "fail", "reason": str(e)}
                return results
        elif cap == "reporting":
            if runtime_dir.is_dir() and (runtime_dir.stat().st_mode & 0o200):
                results[f"capability:{cap}"] = {"status": "pass", "probe": "runtime dir is writable"}
            else:
                results[f"capability:{cap}"] = {"status": "fail", "reason": "runtime dir is not writable"}
                return results

    # min_schema_version check
    min_ver = requires.get("min_schema_version")
    if min_ver is not None:
        state_path = runtime_dir / "execution-state.json"
        if state_path.exists():
            state = json.loads(state_path.read_text())
            ver = state.get("schema_version", 0)
            if ver < min_ver:
                results["min_schema_version"] = {"status": "fail", "reason": f"schema_version {ver} < {min_ver}"}
                return results
            results["min_schema_version"] = {"status": "pass", "version": ver}
        else:
            results["min_schema_version"] = {"status": "pass", "reason": "no state file yet"}

    return results


def pattern_identity(record: dict) -> dict:
    """Extract the semantic identity fields of a pattern (excludes merge-volatile fields like confidence, evidence)."""
    return {
        "pattern_id": record.get("pattern_id"),
        "summary": record.get("summary"),
        "trigger": record.get("trigger"),
        "sequence": parse_csv(record["sequence"]) if isinstance(record.get("sequence"), str) else record.get("sequence", []),
        "outcome": record.get("outcome"),
        "tags": parse_csv(record["tags"]) if isinstance(record.get("tags"), str) else record.get("tags", []),
        "modes": parse_csv(record["modes"]) if isinstance(record.get("modes"), str) else record.get("modes", []),
        "lifecycle_state": record.get("lifecycle_state", "experimental"),
        "asset_version": record.get("asset_version", 2),
    }


def check_idempotent(manifest: dict, runtime_dir: Path, base: Path) -> tuple[bool, dict]:
    """Check if existing assets match the manifest by normalized full content.

    Returns (skipped, details) where details documents what was compared.

    - Adapters: strict full-content match (exact set, all fields).
    - Rules: strict full-content match (exact set, all fields).
      Extra learned rules count as drift — bootstrap re-registers to
      ensure the manifest baseline is present and unmodified.
    - Patterns: semantic identity match on behavioral fields (pattern_id,
      trigger, sequence, outcome, summary, tags, modes, lifecycle_state).
      confidence and evidence are merge-volatile — calling capture on an
      existing pattern always bumps confidence via merge_confidence(),
      so strict comparison would make bootstrap never skip.  Re-registering
      when only confidence drifted would bump it further, making each
      bootstrap run mutate state.  Skipping is the correct idempotent
      behavior when behavioral fields are unchanged.
    """
    details = {}

    # Check adapters — exact set match
    adapters_path = runtime_dir / "adapters.json"
    if adapters_path.exists():
        existing = json.loads(adapters_path.read_text())
        existing_normalized = {a["tool"]: normalize_adapter(a) for a in existing.get("adapters", [])}
        manifest_normalized = {normalize_adapter(a)["tool"]: normalize_adapter(a) for a in manifest.get("adapters", [])}
        if existing_normalized != manifest_normalized:
            details["adapters"] = "drift"
            return False, details
        details["adapters"] = "match"
    else:
        details["adapters"] = "missing"
        return False, details

    # Check rules — exact set match (extra learned rules = drift)
    rules_path = runtime_dir / "rules.json"
    if rules_path.exists():
        existing = json.loads(rules_path.read_text())
        existing_normalized = {r["rule_id"]: normalize_rule(r) for r in existing.get("rules", [])}
        manifest_normalized = {normalize_rule(r)["rule_id"]: normalize_rule(r) for r in manifest.get("rules", [])}
        if existing_normalized != manifest_normalized:
            details["rules"] = "drift"
            return False, details
        details["rules"] = "match"
    else:
        details["rules"] = "missing"
        return False, details

    # Check patterns — semantic identity match (confidence/evidence are merge-volatile)
    patterns_path = runtime_dir / "success-patterns.json"
    if patterns_path.exists():
        existing = json.loads(patterns_path.read_text())
        existing_ids = {p["pattern_id"]: pattern_identity(p) for p in existing.get("patterns", [])}
        manifest_ids = {}
        for p in manifest.get("patterns", []):
            pi = pattern_identity(p)
            manifest_ids[pi["pattern_id"]] = pi
        # All manifest patterns must exist with matching identity
        for pat_id, pat in manifest_ids.items():
            if pat_id not in existing_ids or existing_ids[pat_id] != pat:
                details["patterns"] = f"drift:{pat_id}"
                return False, details
        # Extra patterns beyond manifest are OK (learned patterns)
        details["patterns"] = "match"
    else:
        details["patterns"] = "missing"
        return False, details

    return True, details


def register_adapters(base: Path, manifest: dict, runtime_dir: Path) -> int:
    """Register adapters from manifest via polaris_adapters.py add."""
    count = 0
    for adapter in manifest.get("adapters", []):
        cmd = [
            sys.executable, str(base / "polaris_adapters.py"), "add",
            "--registry", str(runtime_dir / "adapters.json"),
            "--tool", adapter["tool"],
            "--tool-command", adapter["command"],
            "--inputs", adapter.get("inputs", ""),
            "--capabilities", adapter.get("capabilities", ""),
            "--modes", adapter.get("modes", "short,long"),
            "--prerequisites", adapter.get("prerequisites", ""),
            "--selectors", adapter.get("selectors", ""),
            "--failure-notes", adapter.get("failure_notes", ""),
            "--fallbacks", adapter.get("fallbacks", ""),
            "--fallback-notes", adapter.get("fallback_notes", ""),
            "--mode-preferences", adapter.get("mode_preferences", ""),
            "--trust-level", adapter.get("trust_level", "workspace"),
            "--cost-hint", str(adapter.get("cost_hint", 1)),
            "--latency-hint", str(adapter.get("latency_hint", 1)),
            "--preferred-failures", adapter.get("preferred_failures", ""),
            "--safe-retry", adapter.get("safe_retry", "yes"),
            "--notes", adapter.get("notes", ""),
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        count += 1
    return count


def register_rules(base: Path, manifest: dict, runtime_dir: Path) -> int:
    """Register rules from manifest via polaris_rules.py add."""
    count = 0
    for rule in manifest.get("rules", []):
        cmd = [
            sys.executable, str(base / "polaris_rules.py"), "add",
            "--rules", str(runtime_dir / "rules.json"),
            "--rule-id", rule["rule_id"],
            "--layer", rule["layer"],
            "--trigger", rule["trigger"],
            "--action", rule["action"],
            "--evidence", rule["evidence"],
            "--scope", rule["scope"],
            "--tags", rule.get("tags", ""),
            "--validation", rule.get("validation", "observed local evidence"),
            "--priority", str(rule.get("priority", 50)),
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        count += 1
    return count


def register_patterns(base: Path, manifest: dict, runtime_dir: Path) -> int:
    """Register patterns from manifest via polaris_success_patterns.py capture."""
    count = 0
    for pattern in manifest.get("patterns", []):
        # Resolve relative evidence paths against the project root
        evidence = pattern.get("evidence", "")
        if evidence and not evidence.startswith("/"):
            evidence = str(base.parent / evidence)
        cmd = [
            sys.executable, str(base / "polaris_success_patterns.py"), "capture",
            "--patterns", str(runtime_dir / "success-patterns.json"),
            "--pattern-id", pattern["pattern_id"],
            "--summary", pattern["summary"],
            "--trigger", pattern["trigger"],
            "--sequence", pattern["sequence"],
            "--outcome", pattern["outcome"],
            "--evidence", evidence,
            "--tags", pattern.get("tags", ""),
            "--modes", pattern.get("modes", "long"),
            "--confidence", str(pattern.get("confidence", 60)),
            "--lifecycle-state", pattern.get("lifecycle_state", "experimental"),
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap a Polaris runtime directory from a manifest.")
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap_parser = sub.add_parser("bootstrap")
    bootstrap_parser.add_argument("--manifest", required=True)
    bootstrap_parser.add_argument("--runtime-dir", required=True)

    args = parser.parse_args()
    base = Path(__file__).resolve().parent
    runtime_dir = Path(args.runtime_dir).resolve()
    manifest_path = Path(args.manifest).resolve()

    # Load and validate manifest
    manifest = json.loads(manifest_path.read_text())
    allowed_top = {"bootstrap_version", "requires", "adapters", "rules", "patterns"}
    unknown = set(manifest.keys()) - allowed_top
    if unknown:
        print(f"Bootstrap error: unknown manifest fields: {unknown}", file=sys.stderr)
        raise SystemExit(1)
    for field in ("bootstrap_version", "requires", "adapters"):
        if field not in manifest:
            print(f"Bootstrap error: missing required manifest field: {field}", file=sys.stderr)
            raise SystemExit(1)

    # Validate requirements against host environment
    requires_check = check_requires(manifest["requires"], runtime_dir)
    for key, result in requires_check.items():
        if result["status"] == "fail":
            print(f"Bootstrap requirement failed: {key}: {result['reason']}", file=sys.stderr)
            raise SystemExit(1)

    # Idempotency check
    skipped, idempotency_details = check_idempotent(manifest, runtime_dir, base)
    if skipped:
        report = {
            "bootstrap_version": manifest.get("bootstrap_version", 1),
            "manifest": str(manifest_path),
            "adapters_registered": 0,
            "rules_registered": 0,
            "patterns_registered": 0,
            "skipped": True,
            "requires_check": requires_check,
            "idempotency_check": idempotency_details,
        }
        (runtime_dir / "runtime-bootstrap-report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, sort_keys=True))
        return

    # Register assets
    adapters_count = register_adapters(base, manifest, runtime_dir)
    rules_count = register_rules(base, manifest, runtime_dir)
    patterns_count = register_patterns(base, manifest, runtime_dir)

    report = {
        "bootstrap_version": manifest.get("bootstrap_version", 1),
        "manifest": str(manifest_path),
        "adapters_registered": adapters_count,
        "rules_registered": rules_count,
        "patterns_registered": patterns_count,
        "skipped": False,
        "requires_check": requires_check,
    }
    (runtime_dir / "runtime-bootstrap-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
