#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""R0: Experience store contract layer for Polaris Platform 2.

Defines the bottom-level rules for experience storage:
  1. Store path resolution (POLARIS_HOME, default, runtime-dir)
  2. Dual-store merge strategy (runtime + global)
  3. Atomic write with concurrent-write detection (fail closed)

All R1-R5 modules use this layer. No module may bypass it.
"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. Store path resolution
# ---------------------------------------------------------------------------

def resolve_global_dir() -> Path:
    """Resolve the global experience directory.

    Priority (high → low):
      1. POLARIS_HOME env var → $POLARIS_HOME/experience/
      2. Default → ~/.polaris/experience/
    """
    polaris_home = os.environ.get("POLARIS_HOME")
    if polaris_home:
        return Path(polaris_home).expanduser().resolve() / "experience"
    return Path.home() / ".polaris" / "experience"


def resolve_paths(runtime_dir: Path | None = None) -> tuple[Path, Path | None]:
    """Return (global_store_dir, runtime_store_dir).

    runtime_store_dir is None when no runtime-dir was provided.
    """
    global_dir = resolve_global_dir()
    if runtime_dir is not None:
        return global_dir, Path(runtime_dir).resolve()
    return global_dir, None


def ensure_dir(path: Path) -> None:
    """Create directory if it doesn't exist. Warns on failure."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"[polaris] warning: cannot create directory {path}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 2. Atomic write with concurrent-write detection
# ---------------------------------------------------------------------------

def _get_mtime(path: Path) -> float | None:
    """Return mtime of path, or None if file doesn't exist."""
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def atomic_write(path: Path, payload: dict, prior_mtime: float | None = None) -> bool:
    """Write JSON payload atomically via temp+rename.

    If prior_mtime is provided (from a preceding read), verify the file hasn't
    been modified by another writer.  If mtime changed → fail closed, refuse to
    write, return False.

    Returns True on success, False on failure (caller should degrade).
    """
    # Concurrent-write detection
    if prior_mtime is not None:
        current_mtime = _get_mtime(path)
        if current_mtime is not None and current_mtime != prior_mtime:
            print(
                f"[polaris] error: concurrent write detected on {path} "
                f"(expected mtime {prior_mtime}, got {current_mtime}). "
                f"Refusing to write — fail closed.",
                file=sys.stderr,
            )
            return False

    try:
        ensure_dir(path.parent)
        data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        # Write to temp file in same directory, then atomic rename
        fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            os.write(fd, data.encode("utf-8"))
            os.close(fd)
            # os.replace is atomic on POSIX and Windows
            os.replace(tmp_path, str(path))
        except Exception:
            os.close(fd) if not os.get_inheritable(fd) else None
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return True
    except OSError as exc:
        print(
            f"[polaris] warning: failed to write {path}: {exc}. "
            f"Degrading to runtime-only.",
            file=sys.stderr,
        )
        return False


# ---------------------------------------------------------------------------
# 3. Safe load with corruption recovery
# ---------------------------------------------------------------------------

def safe_load(path: Path, default_factory: dict | None = None) -> tuple[dict, float | None]:
    """Load a JSON store file safely.

    Returns (payload, mtime).
    - If file doesn't exist → return default, mtime=None
    - If file is corrupt → rename to .bak, return default, mtime=None, warn
    - On success → return parsed payload and mtime (for concurrent-write check)
    """
    if default_factory is None:
        default_factory = {"schema_version": 2, "records": []}

    if not path.exists():
        return dict(default_factory), None

    mtime = _get_mtime(path)
    try:
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        if isinstance(payload, list):
            # Legacy format: bare list of patterns/records.
            # Wrap into a dict using the default_factory's keys as template.
            # Detect whether this is patterns or records by checking default_factory.
            if "patterns" in default_factory:
                payload = {"schema_version": 1, "patterns": payload}
            else:
                payload = {"schema_version": 1, "records": payload}
        if not isinstance(payload, dict):
            raise ValueError("root must be a JSON object or array")
        return payload, mtime
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        # Corruption recovery: rename to .bak, return empty
        bak_path = path.with_suffix(path.suffix + ".bak")
        try:
            shutil.move(str(path), str(bak_path))
            print(
                f"[polaris] warning: {path} is corrupt ({exc}). "
                f"Renamed to {bak_path.name}, starting fresh.",
                file=sys.stderr,
            )
        except OSError as move_exc:
            print(
                f"[polaris] warning: {path} is corrupt ({exc}) "
                f"and could not be backed up ({move_exc}).",
                file=sys.stderr,
            )
        return dict(default_factory), None


# ---------------------------------------------------------------------------
# 4. Dual-store merge
# ---------------------------------------------------------------------------

def merge_failure_stores(runtime_store: dict, global_store: dict) -> dict:
    """Merge runtime and global failure stores for querying.

    Rules:
      - Deduplicate by (matching_key, recorded_at): one copy per unique pair.
        Multiple records for the same matching_key with different recorded_at
        (i.e. different failure events carrying different hints) all survive.
      - When both stores hold the same (mk, recorded_at) pair, keep the one
        with more state progression (stale > not-stale, higher applied_count).
      - Records unique to either store are always included.
      - Source priority: user_correction > auto > prebuilt
    """
    SOURCE_PRIORITY = {"prebuilt": 0, "auto": 1, "user_correction": 2}

    def _rec_key(rec: dict) -> tuple[str, str]:
        mk = rec.get("task_fingerprint", {}).get("matching_key", "")
        rat = rec.get("recorded_at", "")
        return (mk, rat)

    def _pick_better(a: dict, b: dict) -> dict:
        """Between two records with the same (mk, recorded_at), pick the more progressed."""
        # stale trumps non-stale
        if a.get("stale") and not b.get("stale"):
            return a
        if b.get("stale") and not a.get("stale"):
            return b
        # higher applied_count wins (more tracking data)
        a_count = int(a.get("applied_count", 0)) + int(a.get("applied_fail_count", 0))
        b_count = int(b.get("applied_count", 0)) + int(b.get("applied_fail_count", 0))
        if a_count != b_count:
            return a if a_count > b_count else b
        # source priority
        a_pri = SOURCE_PRIORITY.get(a.get("source", "auto"), 1)
        b_pri = SOURCE_PRIORITY.get(b.get("source", "auto"), 1)
        if a_pri != b_pri:
            return a if a_pri > b_pri else b
        return a  # tie → first caller (runtime in typical usage)

    # Index global records by (matching_key, recorded_at)
    global_by_key: dict[tuple[str, str], dict] = {}
    for rec in global_store.get("records", []):
        k = _rec_key(rec)
        if k in global_by_key:
            global_by_key[k] = _pick_better(global_by_key[k], rec)
        else:
            global_by_key[k] = rec

    merged_records = []
    seen_keys: set[tuple[str, str]] = set()
    for rec in runtime_store.get("records", []):
        k = _rec_key(rec)
        if k in global_by_key:
            merged_records.append(_pick_better(rec, global_by_key[k]))
        else:
            merged_records.append(rec)
        seen_keys.add(k)

    # Add global-only records
    for k, rec in global_by_key.items():
        if k not in seen_keys:
            merged_records.append(rec)

    return {"schema_version": 2, "records": merged_records}


def merge_success_stores(runtime_store: dict, global_store: dict) -> dict:
    """Merge runtime and global success pattern stores for querying.

    Deduplicate by fingerprint: when both stores have the same fingerprint,
    keep the one with the newer updated_at (or higher confidence as tiebreaker).
    This prevents stale runtime copies from shadowing updated global patterns.
    """
    def _pick_newer_pattern(a: dict, b: dict) -> dict:
        """Between two patterns with the same fingerprint, pick the more current one."""
        # stale trumps non-stale
        if a.get("stale") and not b.get("stale"):
            return a
        if b.get("stale") and not a.get("stale"):
            return b
        # compare updated_at
        a_ts = a.get("updated_at", "")
        b_ts = b.get("updated_at", "")
        if a_ts != b_ts:
            return a if a_ts > b_ts else b
        # tiebreaker: higher confidence
        a_conf = int(a.get("confidence", 0))
        b_conf = int(b.get("confidence", 0))
        if a_conf != b_conf:
            return a if a_conf > b_conf else b
        return a

    global_by_fp: dict[str, dict] = {}
    for pat in global_store.get("patterns", []):
        fp = pat.get("fingerprint", "")
        if fp:
            # If multiple globals share a fingerprint, keep the newest
            if fp in global_by_fp:
                global_by_fp[fp] = _pick_newer_pattern(global_by_fp[fp], pat)
            else:
                global_by_fp[fp] = pat

    merged_patterns = []
    seen_fps: set[str] = set()
    for pat in runtime_store.get("patterns", []):
        fp = pat.get("fingerprint", "")
        if fp and fp in global_by_fp:
            merged_patterns.append(_pick_newer_pattern(pat, global_by_fp[fp]))
            seen_fps.add(fp)
        else:
            merged_patterns.append(pat)
            if fp:
                seen_fps.add(fp)

    # Add global-only patterns
    for fp, pat in global_by_fp.items():
        if fp not in seen_fps:
            merged_patterns.append(pat)

    return {"schema_version": max(runtime_store.get("schema_version", 1),
                                   global_store.get("schema_version", 1)),
            "patterns": merged_patterns}


# ---------------------------------------------------------------------------
# 5. Sync: runtime → global
# ---------------------------------------------------------------------------

def sync_failure_to_global(runtime_store: dict, global_path: Path) -> bool:
    """Sync runtime failure records to the global store.

    New records (by matching_key + recorded_at) are appended.
    Stale/rejected updates are propagated.
    Returns True on success.
    """
    global_store, global_mtime = safe_load(
        global_path,
        default_factory={"schema_version": 2, "records": []},
    )

    # Build index of global records by (matching_key, recorded_at) for dedup
    global_index: set[tuple[str, str]] = set()
    global_by_mk: dict[str, list[dict]] = {}
    for rec in global_store.get("records", []):
        mk = rec.get("task_fingerprint", {}).get("matching_key", "")
        rat = rec.get("recorded_at", "")
        global_index.add((mk, rat))
        if mk:
            global_by_mk.setdefault(mk, []).append(rec)

    changed = False
    for rec in runtime_store.get("records", []):
        mk = rec.get("task_fingerprint", {}).get("matching_key", "")
        rat = rec.get("recorded_at", "")
        key = (mk, rat)

        if key not in global_index:
            # New record — append
            global_store["records"].append(rec)
            global_index.add(key)
            changed = True
        else:
            # Existing record — propagate stale/rejected state
            if rec.get("stale") or rec.get("rejected_by"):
                for g_rec in global_by_mk.get(mk, []):
                    if g_rec.get("recorded_at") == rat:
                        if rec.get("stale") and not g_rec.get("stale"):
                            g_rec["stale"] = True
                            changed = True
                        if rec.get("rejected_by") and not g_rec.get("rejected_by"):
                            g_rec["rejected_by"] = rec["rejected_by"]
                            changed = True

    if changed:
        return atomic_write(global_path, global_store, prior_mtime=global_mtime)
    return True


def sync_success_to_global(runtime_store: dict, global_path: Path) -> bool:
    """Sync runtime success patterns to the global store.

    New patterns (by fingerprint) are appended.
    Existing patterns are updated if runtime has newer confidence/stale state.
    Returns True on success.
    """
    global_store, global_mtime = safe_load(
        global_path,
        default_factory={"schema_version": 1, "patterns": []},
    )

    global_by_fp: dict[str, dict] = {}
    global_fps: set[str] = set()
    for pat in global_store.get("patterns", []):
        fp = pat.get("fingerprint", "")
        if fp:
            global_fps.add(fp)
            global_by_fp[fp] = pat

    changed = False
    for pat in runtime_store.get("patterns", []):
        fp = pat.get("fingerprint", "")
        if fp and fp not in global_fps:
            global_store["patterns"].append(pat)
            global_fps.add(fp)
            changed = True
        elif fp and fp in global_by_fp:
            # R2: Propagate confidence/stale/reuse-count updates
            g_pat = global_by_fp[fp]
            rt_updated = pat.get("updated_at", "")
            gl_updated = g_pat.get("updated_at", "")
            if rt_updated > gl_updated:
                for key in ("confidence", "reuse_success_count", "reuse_failure_count",
                            "consecutive_reuse_failures", "updated_at", "lifecycle_state"):
                    if key in pat:
                        g_pat[key] = pat[key]
                if pat.get("stale"):
                    g_pat["stale"] = True
                changed = True

    if changed:
        return atomic_write(global_path, global_store, prior_mtime=global_mtime)
    return True
