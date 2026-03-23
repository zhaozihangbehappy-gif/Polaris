#!/usr/bin/env python3
from __future__ import annotations

import dataclasses
import fcntl
import hashlib
import hmac
import json
import os
import re
import socket
import subprocess
import threading
import time
from pathlib import Path
from typing import Any


DEFAULT_SANITIZER_PATTERNS = {
    "block_wrappers": [
        "MEMORY-CONTEXT",
        "MEETING-CONTEXT",
        "TARGET-CONTEXT",
    ],
    "single_line_headers": [
        "TRIALOGUE-AUDIT",
    ],
}

DEFAULT_VERSION_ALLOWLIST = {
    "policy": "warn",
    "runners": {
        "claude": {"versions": [], "hashes": []},
        "codex": {"versions": [], "hashes": []},
    },
}
SUMMARY_CHAIN_GENESIS_SHA256 = hashlib.sha256(b"TRIALOGUE_V3_SUMMARY_CHAIN_V1").hexdigest()

PORT_PATTERNS = [
    re.compile(r"(?:--port| -p |PORT=|port=)\s*([0-9]{2,5})"),
    re.compile(r"http\.server\s+([0-9]{2,5})"),
    re.compile(r":([0-9]{2,5})(?:\b|/)"),
]
SERVICE_CONTROL_RE = re.compile(
    r"(?:^|[;&|]\s*|\bsudo\s+)(?:systemctl\b|service\s+[a-zA-Z0-9_.@-]+(?:\s+(?:start|stop|restart|reload|status))?\b)",
    re.IGNORECASE,
)
SERVICE_UNIT_RE = re.compile(
    r"(?:systemctl\s+(?:start|stop|restart|reload|status)?\s*|service\s+)([a-zA-Z0-9_.@-]+)",
    re.IGNORECASE,
)
FIREWALL_RE = re.compile(r"\b(?:iptables|ip6tables|nft)\b", re.IGNORECASE)
CRONTAB_RE = re.compile(r"\b(?:crontab|at)\b", re.IGNORECASE)
ETC_WRITE_RE = re.compile(
    r"(?:^|[;&|]\s*|\bsudo\s+)(?:"
    r"(?:tee|install|cp|mv|ln|sed|perl|python3|python|bash|sh|curl|wget)\b[^\n]*\s(/etc/[^\s\"']+)"
    r"|(?:>|>>)\s*(/etc/[^\s\"']+)"
    r"|(/etc/[^\s\"']+)"
    r")",
    re.IGNORECASE,
)
BLOCK_TAG_TEMPLATE = r"\[(?P<close>/)?(?P<name>{names})(?=[\s\]])(?P<attrs>[\s\S]*?)\]"


def load_conf_map(conf_path: str) -> dict[str, str]:
    conf: dict[str, str] = {}
    try:
        with open(conf_path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                conf[key.strip()] = value.strip()
    except FileNotFoundError:
        return {}
    return conf


def _norm_mode(value: str, *, allowed: set[str], default: str) -> str:
    lowered = (value or "").strip().lower()
    return lowered if lowered in allowed else default


def _safe_float(value: str, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


@dataclasses.dataclass
class HardeningSettings:
    transcript_sanitizer: str
    version_gate: str
    version_gate_recheck: str
    operation_locks: str
    external_audit_anchor: str
    broker_recovery_mode: str
    shared_host_collision_guard: str
    sanitizer_patterns_path: str
    version_allowlist_path: str
    lock_timeout_sec: float
    version_recheck_fast_interval_sec: float
    version_recheck_full_interval_sec: float
    state_root: str
    broker_room_state_dir: str
    private_tmp_dir: str
    shared_meta_dir: str
    port_registry_path: str
    summary_chain_dir: str
    anchor_dir: str
    anchor_key_path: str
    alert_log_path: str


def load_hardening_settings(conf_path: str) -> HardeningSettings:
    conf = load_conf_map(conf_path)
    base_dir = os.path.dirname(conf_path)
    workspace = conf.get("WORKSPACE", base_dir).strip() or base_dir
    state_root = conf.get("TRIALOGUE_STATE_ROOT", os.path.join(workspace, "state")).strip() or os.path.join(workspace, "state")
    audit_log = conf.get("AUDIT_LOG", os.path.join(workspace, "audit.jsonl")).strip() or os.path.join(workspace, "audit.jsonl")
    audit_root = os.path.dirname(audit_log) or state_root
    version_gate = _norm_mode(
        conf.get("HARDENING_VERSION_GATE", "warn"),
        allowed={"disabled", "warn", "enforce"},
        default="warn",
    )
    version_gate_recheck = _norm_mode(
        conf.get("HARDENING_VERSION_GATE_RECHECK", version_gate),
        allowed={"disabled", "warn", "enforce"},
        default=version_gate,
    )
    rank = {"disabled": 0, "warn": 1, "enforce": 2}
    if rank[version_gate_recheck] < rank[version_gate]:
        version_gate_recheck = version_gate
    return HardeningSettings(
        transcript_sanitizer=_norm_mode(
            conf.get("HARDENING_TRANSCRIPT_SANITIZER", "strict"),
            allowed={"disabled", "permissive", "strict"},
            default="strict",
        ),
        version_gate=version_gate,
        version_gate_recheck=version_gate_recheck,
        operation_locks="enabled" if conf.get("HARDENING_OPERATION_LOCKS", "enabled").strip().lower() != "disabled" else "disabled",
        external_audit_anchor=_norm_mode(
            conf.get("HARDENING_EXTERNAL_AUDIT_ANCHOR", "disabled"),
            allowed={"disabled", "async", "blocking"},
            default="disabled",
        ),
        broker_recovery_mode=_norm_mode(
            conf.get("HARDENING_BROKER_RECOVERY_MODE", "auto"),
            allowed={"auto", "strict"},
            default="auto",
        ),
        shared_host_collision_guard="enabled" if conf.get("HARDENING_SHARED_HOST_COLLISION_GUARD", "enabled").strip().lower() != "disabled" else "disabled",
        sanitizer_patterns_path=conf.get(
            "HARDENING_SANITIZER_PATTERNS",
            os.path.join(base_dir, "sanitizer-patterns.json"),
        ),
        version_allowlist_path=conf.get(
            "HARDENING_VERSION_ALLOWLIST",
            os.path.join(base_dir, "runner-version-allowlist.json"),
        ),
        lock_timeout_sec=_safe_float(conf.get("HARDENING_LOCK_TIMEOUT_SEC", "30"), 30.0),
        version_recheck_fast_interval_sec=_safe_float(
            conf.get("HARDENING_VERSION_RECHECK_FAST_INTERVAL_SEC", "10"),
            10.0,
        ),
        version_recheck_full_interval_sec=_safe_float(
            conf.get("HARDENING_VERSION_RECHECK_FULL_INTERVAL_SEC", "60"),
            60.0,
        ),
        state_root=state_root,
        broker_room_state_dir=conf.get("BROKER_ROOM_STATE_DIR", os.path.join(state_root, "broker-rooms")).strip() or os.path.join(state_root, "broker-rooms"),
        private_tmp_dir=conf.get("TRIALOGUE_PRIVATE_TMP_DIR", os.path.join(state_root, "tmp")).strip() or os.path.join(state_root, "tmp"),
        shared_meta_dir=conf.get("TRIALOGUE_SHARED_META_DIR", os.path.join(state_root, "shared-meta")).strip() or os.path.join(state_root, "shared-meta"),
        port_registry_path=conf.get("TRIALOGUE_PORT_REGISTRY_PATH", os.path.join(state_root, "port-registry.json")).strip() or os.path.join(state_root, "port-registry.json"),
        summary_chain_dir=conf.get("HARDENING_SUMMARY_CHAIN_DIR", os.path.join(audit_root, "summary-chain")).strip() or os.path.join(audit_root, "summary-chain"),
        anchor_dir=conf.get("HARDENING_ANCHOR_DIR", os.path.join(audit_root, "anchor")).strip() or os.path.join(audit_root, "anchor"),
        anchor_key_path=conf.get("HARDENING_ANCHOR_KEY_PATH", os.path.join(audit_root, "anchor.key")).strip() or os.path.join(audit_root, "anchor.key"),
        alert_log_path=conf.get(
            "HARDENING_ALERT_LOG",
            os.path.join(base_dir, "hardening-events.jsonl"),
        ),
    )


def _load_json(path: str, default: dict[str, Any]) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
            return payload if isinstance(payload, dict) else default
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def load_sanitizer_patterns(path: str) -> dict[str, Any]:
    payload = _load_json(path, DEFAULT_SANITIZER_PATTERNS)
    block_wrappers = payload.get("block_wrappers") or []
    single_line_headers = payload.get("single_line_headers") or []
    return {
        "block_wrappers": [str(x).strip() for x in block_wrappers if str(x).strip()],
        "single_line_headers": [str(x).strip() for x in single_line_headers if str(x).strip()],
    }


def load_version_allowlist(path: str) -> dict[str, Any]:
    payload = _load_json(path, DEFAULT_VERSION_ALLOWLIST)
    runners = payload.get("runners") or {}
    normalized = {"policy": payload.get("policy", "warn"), "runners": {}}
    for name in ("claude", "codex"):
        rule = runners.get(name) or {}
        normalized["runners"][name] = {
            "versions": [str(x).strip() for x in (rule.get("versions") or []) if str(x).strip()],
            "hashes": [str(x).strip() for x in (rule.get("hashes") or []) if str(x).strip()],
        }
    return normalized


@dataclasses.dataclass
class TranscriptSanitizerMeta:
    mode: str
    raw_entry_count: int
    injected_entry_count: int
    modifications_count: int
    removed_wrapper_types: list[str]
    notice: str
    sanitized: bool


def _sanitize_text_once(text: str, patterns: dict[str, Any]) -> tuple[str, int, list[str]]:
    updated = text or ""
    modifications = 0
    removed: list[str] = []
    block_wrappers = [wrapper for wrapper in patterns.get("block_wrappers", []) if wrapper]
    if block_wrappers:
        names_expr = "|".join(re.escape(wrapper) for wrapper in block_wrappers)
        token_re = re.compile(BLOCK_TAG_TEMPLATE.format(names=names_expr), re.IGNORECASE)
        stack: list[tuple[str, int]] = []
        spans: list[tuple[int, int]] = []
        for match in token_re.finditer(updated):
            name = (match.group("name") or "").upper()
            is_close = bool(match.group("close"))
            if not is_close:
                stack.append((name, match.start()))
                continue
            close_end = match.end()
            if not stack:
                spans.append((match.start(), close_end))
                modifications += 1
                removed.append(name)
                continue
            same_index = next((idx for idx in range(len(stack) - 1, -1, -1) if stack[idx][0] == name), -1)
            if same_index >= 0:
                open_name, open_start = stack[same_index]
                spans.append((open_start, close_end))
                removed.extend(item_name for item_name, _ in stack[same_index:])
                removed.append(name)
                modifications += 1
                stack = stack[:same_index]
            else:
                spans.append((match.start(), close_end))
                modifications += 1
                removed.append(name)
        for open_name, open_start in stack:
            spans.append((open_start, len(updated)))
            modifications += 1
            removed.append(open_name)
        if spans:
            spans.sort()
            merged: list[tuple[int, int]] = []
            for start, end in spans:
                if not merged or start > merged[-1][1]:
                    merged.append((start, end))
                else:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            parts: list[str] = []
            cursor = 0
            for start, end in merged:
                parts.append(updated[cursor:start])
                cursor = end
            parts.append(updated[cursor:])
            updated = "".join(parts)
    for wrapper in patterns.get("single_line_headers", []):
        expr = re.compile(rf"^\[{re.escape(wrapper)}[^\]]*\]\s*$", re.IGNORECASE | re.MULTILINE)
        updated, count = expr.subn("", updated)
        if count:
            modifications += count
            removed.extend([wrapper] * count)
    updated = re.sub(r"\n{3,}", "\n\n", updated).strip()
    return updated, modifications, removed


def sanitize_transcript_entries(
    entries: list[dict[str, str]],
    *,
    settings: HardeningSettings,
) -> tuple[list[dict[str, str]], TranscriptSanitizerMeta]:
    raw_count = len(entries)
    if settings.transcript_sanitizer == "disabled":
        return entries, TranscriptSanitizerMeta(
            mode="disabled",
            raw_entry_count=raw_count,
            injected_entry_count=raw_count,
            modifications_count=0,
            removed_wrapper_types=[],
            notice="",
            sanitized=False,
        )

    patterns = load_sanitizer_patterns(settings.sanitizer_patterns_path)
    sanitized_entries: list[dict[str, str]] = []
    modifications = 0
    removed_all: list[str] = []

    for entry in entries:
        text = entry.get("text", "")
        updated, count, removed = _sanitize_text_once(text, patterns)
        modifications += count
        removed_all.extend(removed)
        if settings.transcript_sanitizer == "permissive" and count:
            updated = text
        sanitized_entries.append({"speaker": entry.get("speaker", ""), "text": updated})

    notice = ""
    if modifications > 0:
        notice = f"Transcript security filter removed {modifications} control-like fragments."
    return sanitized_entries, TranscriptSanitizerMeta(
        mode=settings.transcript_sanitizer,
        raw_entry_count=raw_count,
        injected_entry_count=len(sanitized_entries),
        modifications_count=modifications,
        removed_wrapper_types=sorted(set(removed_all)),
        notice=notice,
        sanitized=modifications > 0,
    )


def resolve_versioned_binary(target: str, conf_path: str) -> str:
    conf = load_conf_map(conf_path)
    if target == "claude":
        return conf.get("CLAUDE_BIN", "")
    if conf.get("CODEX_APP_SERVER_BIN"):
        return conf.get("CODEX_APP_SERVER_BIN", "")
    return conf.get("CODEX_BIN", "")


def _version_rule_match(target: str, snapshot: dict[str, Any], settings: HardeningSettings) -> tuple[bool, str]:
    allowlist = load_version_allowlist(settings.version_allowlist_path)
    rule = (allowlist.get("runners") or {}).get(target) or {}
    allowed_versions = set(rule.get("versions") or [])
    allowed_hashes = set(rule.get("hashes") or [])
    version = snapshot.get("cli_version", "")
    sha = snapshot.get("binary_sha256", "")
    matched = bool((version and version in allowed_versions) or (sha and sha in allowed_hashes))
    reason = "allowlist matched" if matched else "runner binary is outside version/hash allowlist"
    return matched, reason


def _snapshot_identity_fields(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "binary_path": snapshot.get("binary_path", ""),
        "binary_exists": bool(snapshot.get("binary_exists")),
        "binary_sha256": snapshot.get("binary_sha256", ""),
        "cli_version": snapshot.get("cli_version", ""),
    }


def _snapshot_changed_fields(startup_snapshot: dict[str, Any], invocation_snapshot: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    startup_fields = _snapshot_identity_fields(startup_snapshot)
    invocation_fields = _snapshot_identity_fields(invocation_snapshot)
    for key, startup_value in startup_fields.items():
        if invocation_fields.get(key) != startup_value:
            changed.append(key)
    return changed


def snapshot_runner_version(
    target: str,
    conf_path: str,
    *,
    settings: HardeningSettings | None = None,
    previous_snapshot: dict[str, Any] | None = None,
    force_full: bool = False,
) -> dict[str, Any]:
    bin_path = resolve_versioned_binary(target, conf_path)
    resolved = str(Path(bin_path).resolve()) if bin_path else ""
    sha = ""
    version = "missing"
    exists = bool(bin_path and os.path.lexists(bin_path))
    checked_at = time.time()
    full_hash_at = checked_at
    size = 0
    mtime_ns = 0
    snapshot_mode = "missing"
    version_probe_ran = False
    stat_changed = True
    stat_unchanged = False
    stat_result = None
    if exists:
        try:
            stat_result = os.stat(bin_path)
            size = int(stat_result.st_size)
            mtime_ns = int(getattr(stat_result, "st_mtime_ns", int(stat_result.st_mtime * 1_000_000_000)))
        except OSError:
            stat_result = None
    if previous_snapshot and exists and stat_result is not None:
        prev_path = str(previous_snapshot.get("binary_path", ""))
        prev_size = int(previous_snapshot.get("binary_size", 0) or 0)
        prev_mtime_ns = int(previous_snapshot.get("binary_mtime_ns", 0) or 0)
        prev_checked_at = float(previous_snapshot.get("checked_at", 0) or 0)
        prev_full_hash_at = float(previous_snapshot.get("full_hash_at", 0) or 0)
        stat_unchanged = (
            prev_path == (resolved or bin_path)
            and prev_size == size
            and prev_mtime_ns == mtime_ns
        )
        stat_changed = not stat_unchanged
        if (
            settings is not None
            and not force_full
            and stat_unchanged
            and (checked_at - prev_checked_at) <= settings.version_recheck_fast_interval_sec
            and (checked_at - prev_full_hash_at) <= settings.version_recheck_full_interval_sec
        ):
            snapshot_mode = "stat_only"
            sha = str(previous_snapshot.get("binary_sha256", ""))
            version = str(previous_snapshot.get("cli_version", "unknown"))
            full_hash_at = prev_full_hash_at or checked_at
    if exists and snapshot_mode != "stat_only":
        snapshot_mode = "full"
        version_probe_ran = True
        full_hash_at = checked_at
        try:
            sha = hashlib.sha256(Path(bin_path).read_bytes()).hexdigest()
        except OSError:
            sha = ""
        try:
            proc = subprocess.run(
                [bin_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=5,
            )
            version = (proc.stdout or proc.stderr or "").strip() or "unknown"
        except (OSError, subprocess.SubprocessError):
            version = "unknown"
    return {
        "target": target,
        "binary_path": resolved or bin_path,
        "binary_exists": exists,
        "binary_sha256": sha,
        "cli_version": version,
        "binary_size": size,
        "binary_mtime_ns": mtime_ns,
        "checked_at": checked_at,
        "full_hash_at": full_hash_at,
        "snapshot_mode": snapshot_mode,
        "version_probe_ran": version_probe_ran,
        "stat_changed": stat_changed if exists else False,
    }


def evaluate_version_gate(
    target: str,
    snapshot: dict[str, Any],
    *,
    settings: HardeningSettings,
) -> dict[str, Any]:
    policy = settings.version_gate if settings.version_gate != "disabled" else "disabled"
    matched, reason = _version_rule_match(target, snapshot, settings)
    if policy == "disabled":
        return {"policy": policy, "allowed": True, "matched": matched, "reason": "version gate disabled"}
    if matched:
        return {"policy": policy, "allowed": True, "matched": True, "reason": "allowlist matched"}
    return {
        "policy": policy,
        "allowed": policy != "enforce",
        "matched": False,
        "reason": reason,
    }


def evaluate_version_recheck(
    target: str,
    startup_snapshot: dict[str, Any],
    invocation_snapshot: dict[str, Any],
    *,
    settings: HardeningSettings,
) -> dict[str, Any]:
    policy = settings.version_gate_recheck
    changed_fields = _snapshot_changed_fields(startup_snapshot, invocation_snapshot)
    changed = bool(changed_fields)
    matched, gate_reason = _version_rule_match(target, invocation_snapshot, settings)
    if policy == "disabled":
        return {
            "policy": policy,
            "allowed": True,
            "result": "disabled",
            "matched": matched,
            "changed": changed,
            "changed_fields": changed_fields,
            "reason": "version recheck disabled",
        }
    if not invocation_snapshot.get("binary_exists"):
        return {
            "policy": policy,
            "allowed": policy != "enforce",
            "result": "missing",
            "matched": False,
            "changed": True,
            "changed_fields": changed_fields or ["binary_exists"],
            "reason": "runner binary missing at invocation time",
        }
    if not changed:
        return {
            "policy": policy,
            "allowed": True,
            "result": "match",
            "matched": matched,
            "changed": False,
            "changed_fields": [],
            "reason": "invocation snapshot matches startup snapshot",
        }
    if matched:
        return {
            "policy": policy,
            "allowed": True,
            "result": "changed-but-allowed",
            "matched": True,
            "changed": True,
            "changed_fields": changed_fields,
            "reason": "runner changed after startup but still matches allowlist",
        }
    return {
        "policy": policy,
        "allowed": policy != "enforce",
        "result": "changed-and-unapproved",
        "matched": False,
        "changed": True,
        "changed_fields": changed_fields,
        "reason": gate_reason,
    }


def classify_operation(request: dict[str, Any] | None) -> dict[str, Any]:
    request = request or {}
    command = " ".join(
        str(part)
        for part in [
            request.get("command", ""),
            request.get("reason", ""),
            json.dumps(request.get("commandActions", []), ensure_ascii=False),
        ]
        if part
    )
    lower = command.lower()
    cwd = str(request.get("cwd", "") or "")

    for expr in PORT_PATTERNS:
        match = expr.search(command)
        if match:
            port = match.group(1)
            return {
                "class_name": "ports",
                "resource_name": f"port:{port}",
                "operation_type": "host_port",
                "requires_lock": True,
                "heuristic": "command_port_match",
                "summary": f"host port {port}",
            }

    for pkg in ("apt-get", "apt", "dpkg", "pnpm", "npm", "pip3", "pip", "cargo install", "cargo"):
        if pkg in lower:
            tool = "cargo" if pkg.startswith("cargo") else pkg
            return {
                "class_name": "pkgmgr",
                "resource_name": f"pkgmgr:{tool}",
                "operation_type": "host_package_manager",
                "requires_lock": True,
                "heuristic": "package_manager_match",
                "summary": f"package manager {tool}",
            }

    if SERVICE_CONTROL_RE.search(command):
        unit_match = SERVICE_UNIT_RE.search(command)
        unit = unit_match.group(1) if unit_match else "system"
        return {
            "class_name": "systemd",
            "resource_name": f"systemd:{unit}",
            "operation_type": "host_service_control",
            "requires_lock": True,
            "heuristic": "service_control_match",
            "summary": f"service {unit}",
        }

    if FIREWALL_RE.search(command):
        tool_match = FIREWALL_RE.search(command)
        tool = tool_match.group(0).lower() if tool_match else "firewall"
        return {
            "class_name": "systemd",
            "resource_name": f"firewall:{tool}",
            "operation_type": "host_service_control",
            "requires_lock": True,
            "heuristic": "firewall_rule_match",
            "summary": f"firewall rules via {tool}",
        }

    etc_match = ETC_WRITE_RE.search(command)
    if etc_match:
        target_path = next((group for group in etc_match.groups() if group), "/etc")
        return {
            "class_name": "systemd",
            "resource_name": f"etc:{target_path}",
            "operation_type": "host_service_control",
            "requires_lock": True,
            "heuristic": "etc_write_match",
            "summary": f"system config write {target_path}",
        }

    if CRONTAB_RE.search(command):
        tool_match = CRONTAB_RE.search(command)
        tool = tool_match.group(0).lower() if tool_match else "crontab"
        return {
            "class_name": "systemd",
            "resource_name": f"scheduler:{tool}",
            "operation_type": "host_service_control",
            "requires_lock": True,
            "heuristic": "scheduler_match",
            "summary": f"scheduler mutation via {tool}",
        }

    if "/tmp/" in lower or cwd.startswith("/tmp/"):
        path_match = re.search(r"(/tmp/[^\s\"']+)", command)
        path = path_match.group(1) if path_match else (cwd if cwd.startswith("/tmp/") else "/tmp/shared")
        return {
            "class_name": "global_tmp",
            "resource_name": f"tmp:{path}",
            "operation_type": "host_tmp_shared",
            "requires_lock": True,
            "heuristic": "tmp_path_match",
            "summary": f"shared tmp {path}",
        }

    if "/dev/" in lower or any(token in lower for token in ("mount ", "umount ", "modprobe ", "losetup ")):
        dev_match = re.search(r"(/dev/[^\s\"']+)", command)
        resource = dev_match.group(1) if dev_match else "device"
        return {
            "class_name": "device_access",
            "resource_name": f"device:{resource}",
            "operation_type": "host_device",
            "requires_lock": True,
            "heuristic": "device_match",
            "summary": f"device access {resource}",
        }

    return {
        "class_name": "workspace_local",
        "resource_name": "",
        "operation_type": "workspace_local",
        "requires_lock": False,
        "heuristic": "default_workspace_local",
        "summary": "workspace-local operation",
    }


@dataclasses.dataclass
class LockDecision:
    granted: bool
    wait_sec: float
    class_lock: str
    resource_lock: str
    reason: str
    blocking_owner: str


class HostOperationLockManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owners: dict[str, str] = {}

    def acquire(self, owner: str, class_name: str, resource_name: str, timeout_sec: float) -> LockDecision:
        class_lock = f"class:{class_name}"
        resource_lock = f"resource:{resource_name}" if resource_name else ""
        needed = [class_lock] + ([resource_lock] if resource_lock else [])
        start = time.monotonic()
        while True:
            with self._lock:
                blocking_owner = ""
                blocked = False
                for lock_name in needed:
                    holder = self._owners.get(lock_name)
                    if holder and holder != owner:
                        blocked = True
                        blocking_owner = holder
                        break
                if not blocked:
                    for lock_name in needed:
                        self._owners[lock_name] = owner
                    return LockDecision(
                        granted=True,
                        wait_sec=time.monotonic() - start,
                        class_lock=class_lock,
                        resource_lock=resource_lock,
                        reason="acquired",
                        blocking_owner="",
                    )
            if time.monotonic() - start >= timeout_sec:
                return LockDecision(
                    granted=False,
                    wait_sec=time.monotonic() - start,
                    class_lock=class_lock,
                    resource_lock=resource_lock,
                    reason="timeout",
                    blocking_owner=blocking_owner,
                )
            time.sleep(0.1)

    def release_owner(self, owner: str) -> None:
        with self._lock:
            for key in [name for name, holder in self._owners.items() if holder == owner]:
                self._owners.pop(key, None)

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._owners)


def ensure_parent_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def atomic_write_json(path: str, payload: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def read_json_file(path: str, default: dict[str, Any] | None = None) -> dict[str, Any]:
    fallback = {} if default is None else default
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
            return payload if isinstance(payload, dict) else fallback
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def append_jsonl(path: str, payload: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def _last_jsonl_record(path: str) -> dict[str, Any] | None:
    try:
        last = None
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                last = json.loads(line)
        return last
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _anchor_signature_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_turn_summary(record: dict[str, Any], *, room_id: str, source_mode: str) -> dict[str, Any]:
    confirmation = record.get("confirmation") or {}
    summary = {
        "schema": "trialogue_turn_summary_v1",
        "room_id": room_id,
        "source_mode": source_mode,
        "rid": record.get("rid", ""),
        "nonce": record.get("nonce", ""),
        "target": record.get("target", ""),
        "target_name": record.get("target_name", ""),
        "target_source": record.get("target_source", ""),
        "target_path": record.get("target_path", ""),
        "mode": record.get("mode", ""),
        "session_id": record.get("session_id", ""),
        "session_confirmed": bool(record.get("session_confirmed")),
        "confirmation_method": record.get("confirmation_method", ""),
        "turn_id": confirmation.get("turn_id", ""),
        "thread_id": confirmation.get("thread_id", ""),
        "exit_code": record.get("exit_code"),
        "binary_path": record.get("binary_path", ""),
        "binary_sha256": record.get("binary_sha256", ""),
        "cli_version": record.get("cli_version", ""),
        "version_gate_policy": record.get("version_gate_policy", "disabled"),
        "version_gate_allowed": bool(record.get("version_gate_allowed", True)),
        "version_gate_reason": record.get("version_gate_reason", ""),
        "version_recheck_policy": record.get("version_recheck_policy", "disabled"),
        "version_recheck_allowed": bool(record.get("version_recheck_allowed", True)),
        "version_recheck_result": record.get("version_recheck_result", "disabled"),
        "version_recheck_reason": record.get("version_recheck_reason", ""),
        "message_body_sha256": hashlib.sha256(str(record.get("message_body", "")).encode("utf-8")).hexdigest(),
        "stdout_sha256": hashlib.sha256(str(record.get("stdout", "")).encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(str(record.get("stderr", "")).encode("utf-8")).hexdigest(),
        "raw_event_log_path": record.get("raw_event_log_path", ""),
        "room_state_path": record.get("room_state_path", ""),
        "timestamp": record.get("timestamp", ""),
    }
    canonical = _anchor_signature_bytes(summary)
    summary["turn_summary_sha256"] = hashlib.sha256(canonical).hexdigest()
    return summary


def append_summary_chain(
    summary_chain_dir: str,
    record: dict[str, Any],
    *,
    room_id: str,
    source_mode: str,
) -> dict[str, Any]:
    Path(summary_chain_dir).mkdir(parents=True, exist_ok=True)
    chain_path = os.path.join(summary_chain_dir, f"{room_id}.jsonl")
    lock_path = f"{chain_path}.lock"
    ensure_parent_dir(lock_path)
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        last_record = _last_jsonl_record(chain_path)
        prev_sha = SUMMARY_CHAIN_GENESIS_SHA256
        if last_record:
            prev_sha = str(last_record.get("turn_summary_sha256") or SUMMARY_CHAIN_GENESIS_SHA256)
        summary = build_turn_summary(record, room_id=room_id, source_mode=source_mode)
        entry = {
            "schema": "trialogue_summary_chain_entry_v1",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "room_id": room_id,
            "rid": record.get("rid", ""),
            "target": record.get("target", ""),
            "prev_summary_sha256": prev_sha,
            "turn_summary_sha256": summary["turn_summary_sha256"],
            "summary": summary,
        }
        append_jsonl(chain_path, entry)
    return {
        "chain_path": chain_path,
        "entry": entry,
        "prev_summary_sha256": prev_sha,
        "turn_summary_sha256": summary["turn_summary_sha256"],
        "genesis_summary_sha256": SUMMARY_CHAIN_GENESIS_SHA256,
    }


def export_anchor_bundle(
    anchor_dir: str,
    anchor_key_path: str,
    chain_entry: dict[str, Any],
    *,
    policy: str,
) -> dict[str, Any]:
    if policy == "disabled":
        return {"policy": policy, "status": "disabled", "bundle_path": "", "reason": "anchor disabled"}
    key_bytes = b""
    try:
        key_bytes = Path(anchor_key_path).read_bytes()
    except OSError:
        key_bytes = b""
    if not key_bytes:
        return {
            "policy": policy,
            "status": "failed",
            "bundle_path": "",
            "reason": "anchor signing key missing",
        }
    room_id = chain_entry["entry"]["room_id"]
    turn_sha = chain_entry["turn_summary_sha256"]
    bundle_body = {
        "schema": "trialogue_anchor_bundle_v1",
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "room_id": room_id,
        "rid": chain_entry["entry"].get("rid", ""),
        "target": chain_entry["entry"].get("target", ""),
        "prev_summary_sha256": chain_entry["prev_summary_sha256"],
        "turn_summary_sha256": turn_sha,
        "genesis_summary_sha256": chain_entry["genesis_summary_sha256"],
        "signature_type": "hmac-sha256-local-file",
    }
    signature = hmac.new(key_bytes, _anchor_signature_bytes(bundle_body), hashlib.sha256).hexdigest()
    bundle = {**bundle_body, "signature": signature}
    room_dir = os.path.join(anchor_dir, room_id)
    Path(room_dir).mkdir(parents=True, exist_ok=True)
    bundle_path = os.path.join(room_dir, f"{turn_sha}.json")
    atomic_write_json(bundle_path, bundle)
    return {"policy": policy, "status": "exported", "bundle_path": bundle_path, "reason": ""}


def verify_summary_chain(
    chain_path: str,
    *,
    anchor_dir: str = "",
    anchor_key_path: str = "",
) -> dict[str, Any]:
    checked = 0
    prev_expected = SUMMARY_CHAIN_GENESIS_SHA256
    key_bytes = b""
    if anchor_key_path:
        try:
            key_bytes = Path(anchor_key_path).read_bytes()
        except OSError:
            key_bytes = b""
    try:
        with open(chain_path, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                checked += 1
                entry = json.loads(line)
                prev_actual = entry.get("prev_summary_sha256", "")
                if prev_actual != prev_expected:
                    return {"ok": False, "checked": checked, "reason": "chain prev hash mismatch", "entry": entry}
                summary = entry.get("summary") or {}
                turn_expected = hashlib.sha256(_anchor_signature_bytes({
                    k: v for k, v in summary.items() if k != "turn_summary_sha256"
                })).hexdigest()
                if summary.get("turn_summary_sha256") != turn_expected or entry.get("turn_summary_sha256") != turn_expected:
                    return {"ok": False, "checked": checked, "reason": "summary hash mismatch", "entry": entry}
                if anchor_dir:
                    bundle_path = os.path.join(anchor_dir, entry.get("room_id", ""), f"{turn_expected}.json")
                    if not os.path.isfile(bundle_path):
                        return {"ok": False, "checked": checked, "reason": "anchor bundle missing", "entry": entry}
                    bundle = read_json_file(bundle_path)
                    if bundle.get("turn_summary_sha256") != turn_expected:
                        return {"ok": False, "checked": checked, "reason": "anchor turn hash mismatch", "entry": entry}
                    if key_bytes:
                        signature = bundle.get("signature", "")
                        body = {k: v for k, v in bundle.items() if k != "signature"}
                        expected_sig = hmac.new(key_bytes, _anchor_signature_bytes(body), hashlib.sha256).hexdigest()
                        if signature != expected_sig:
                            return {"ok": False, "checked": checked, "reason": "anchor signature mismatch", "entry": entry}
                prev_expected = turn_expected
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        return {"ok": False, "checked": checked, "reason": str(exc)}
    return {"ok": True, "checked": checked, "reason": "", "genesis_summary_sha256": SUMMARY_CHAIN_GENESIS_SHA256}


class PortReservationRegistry:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._state = read_json_file(path, {"reservations": {}})
        self._state.setdefault("reservations", {})

    def _persist(self) -> None:
        atomic_write_json(self.path, self._state)

    def reserve(self, port: int, owner: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        key = str(port)
        with self._lock:
            current = (self._state.get("reservations") or {}).get(key)
            if current and current.get("owner") != owner:
                return {"granted": False, "reason": "already_reserved", "reservation": current}
            payload = {
                "owner": owner,
                "reserved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "metadata": metadata or {},
            }
            self._state.setdefault("reservations", {})[key] = payload
            self._persist()
            return {"granted": True, "reason": "reserved", "reservation": payload}

    def release_owner(self, owner: str) -> list[str]:
        released: list[str] = []
        with self._lock:
            reservations = self._state.setdefault("reservations", {})
            for key in [name for name, payload in reservations.items() if payload.get("owner") == owner]:
                reservations.pop(key, None)
                released.append(key)
            if released:
                self._persist()
        return released

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def reconcile_after_restart(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        with self._lock:
            reservations = self._state.setdefault("reservations", {})
            updated = False
            for key, payload in list(reservations.items()):
                try:
                    port = int(key)
                except ValueError:
                    reservations.pop(key, None)
                    updated = True
                    events.append({"kind": "port_registry_invalid", "port": key})
                    continue
                if _can_bind_local_port(port):
                    reservations.pop(key, None)
                    updated = True
                    events.append({"kind": "port_registry_orphan_cleaned", "port": port, "owner": payload.get("owner", "")})
                else:
                    payload["metadata"] = {**(payload.get("metadata") or {}), "occupied_after_restart": True}
                    events.append({"kind": "port_registry_occupied", "port": port, "owner": payload.get("owner", "")})
            if updated:
                self._persist()
        return events


def _can_bind_local_port(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def append_hardening_event(path: str, payload: dict[str, Any]) -> None:
    if not path:
        return
    try:
        append_jsonl(path, payload)
    except OSError:
        return
