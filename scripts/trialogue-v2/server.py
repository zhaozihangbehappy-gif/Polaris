#!/usr/bin/env python3
"""
Trialogue v2 Web UI server.

Browser UI only handles display and input forwarding.
All agent execution still goes through launcher.sh -> _audit.py.
"""

import argparse
import base64
import copy
import datetime
import hashlib
import json
import os
import secrets
import socket
import struct
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from chat import (
    build_audit_message,
    build_meeting_context,
    make_room_id,
    build_target_message,
    call_launcher,
    call_launcher_stream,
    has_external_codex_runner,
    parse_message,
    parse_target_command,
    resolve_agent_target_info,
    resolve_target,
)
from _memory import load_memory, build_injected_message
from hardening import (
    HostOperationLockManager,
    PortReservationRegistry,
    atomic_write_json,
    append_hardening_event,
    classify_operation,
    evaluate_version_gate,
    evaluate_version_recheck,
    load_hardening_settings,
    read_json_file,
    snapshot_runner_version,
    verify_remote_anchor,
)


MAX_CLAUDE_HISTORY = 5
MAX_AGENT_EVENTS = 60

def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")


def status_label(status: str, confirmed: bool | None = None) -> str:
    if status == "queued":
        return "已排队"
    if status == "running":
        return "运行中"
    if status == "done" and confirmed is True:
        return "已完成并验真"
    if status == "done" and confirmed is False:
        return "已完成，未验真"
    if status == "failed":
        return "执行失败"
    return "未知状态"


def shorten_command(line: str, limit: int = 88) -> str:
    compact = " ".join(line.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


class TrialogueState:
    def __init__(self, topic: str, launcher: str, conf: str, audit_log: str):
        self.topic = topic
        self.room_id = make_room_id(topic)
        self.launcher = launcher
        self.conf = conf
        self.audit_log = audit_log
        self.hardening = load_hardening_settings(conf)
        os.environ.setdefault("TRIALOGUE_PRIVATE_TMP_DIR", self.hardening.private_tmp_dir)
        os.environ.setdefault("TRIALOGUE_SHARED_META_DIR", self.hardening.shared_meta_dir)
        Path(self.hardening.private_tmp_dir).mkdir(parents=True, exist_ok=True)
        Path(self.hardening.shared_meta_dir).mkdir(parents=True, exist_ok=True)
        Path(self.hardening.broker_room_state_dir).mkdir(parents=True, exist_ok=True)
        self.version_snapshots = {
            target: snapshot_runner_version(target, conf)
            for target in ("claude", "codex")
        }
        self.version_gate = {
            target: evaluate_version_gate(target, self.version_snapshots[target], settings=self.hardening)
            for target in ("claude", "codex")
        }
        self.version_recheck_snapshots = dict(self.version_snapshots)
        self.version_recheck = {
            target: {
                "policy": self.hardening.version_gate_recheck,
                "allowed": True,
                "result": "startup-only",
                "matched": self.version_gate[target]["matched"],
                "changed": False,
                "changed_fields": [],
                "reason": "invocation recheck not run yet",
            }
            for target in ("claude", "codex")
        }
        self.codex_runner_enabled = has_external_codex_runner(conf)
        self.started_at = now_iso()
        self.items: list[dict[str, Any]] = []
        self.system_events: list[dict[str, Any]] = []
        self.degraded_features: dict[str, dict[str, Any]] = {}
        self.last_rid = ""
        self.latest_codex_session = ""
        self.current_claude_session = ""
        self.claude_sessions: list[str] = []
        self.claude_meeting_cursor = 0
        self.codex_meeting_cursor = 0
        self.room_health = "healthy"
        self.recovery_reasons: list[str] = []
        self.remote_anchor = {
            "policy": self.hardening.remote_anchor_publish,
            "state": "disabled" if self.hardening.remote_anchor_publish == "disabled" else "healthy",
            "last_status": "disabled" if self.hardening.remote_anchor_publish == "disabled" else "startup-only",
            "last_reason": "",
            "last_remote_sequence": None,
            "backlog_count": 0,
            "consecutive_unanchored": 0,
            "verify_status": "disabled" if self.hardening.remote_anchor_publish == "disabled" else "startup-pending",
            "verify_reason": "",
            "verify_checked_local": 0,
            "verify_checked_remote": 0,
            "verify_last_sequence": None,
            "verify_last_trigger": "",
            "verify_last_checked_at": "",
            "verify_turn_counter": 0,
            "verify_last_turn": 0,
            "recovery_publish_ready": False,
            "recovery_verify_ready": False,
            "verifier_running": False,
            "updated_at": "",
        }
        self.target_override = ""
        self.clients: set[socket.socket] = set()
        self.lock = threading.RLock()
        self.operation_locks = HostOperationLockManager()
        self.port_registry = PortReservationRegistry(self.hardening.port_registry_path)
        self.claude_exec_lock = threading.Lock()
        self.pending_approvals: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.remote_verify_lock = threading.Lock()
        self.room_state_path = os.path.join(self.hardening.broker_room_state_dir, f"{self.room_id}.json")
        self.persisted_state = read_json_file(self.room_state_path, {})
        self._load_persisted_broker_state()
        self._load_history()
        self._recover_port_registry()
        self.audit_offset = os.path.getsize(self.audit_log) if os.path.isfile(self.audit_log) else 0
        for target, gate in self.version_gate.items():
            if not gate.get("allowed", True):
                self.emit_system_event(
                    "version_gate_block",
                    f"{target} blocked by version gate: {gate.get('reason', 'unknown')}",
                    severity="error",
                    feature="version_gate",
                )
            elif not gate.get("matched", True) and gate.get("policy") == "warn":
                self.emit_system_event(
                    "version_gate_warn",
                    f"{target} is outside allowlist: {gate.get('reason', 'unknown')}",
                    severity="warn",
                    feature="version_gate",
                )
        self._run_remote_verifier(trigger="startup", asynchronous=False)
        self._persist_room_state()
        threading.Thread(target=self._tail_audit_log, daemon=True).start()

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            active_agents = 0
            for item in self.items:
                for agent in item["agents"]:
                    if agent["status"] in ("queued", "running"):
                        active_agents += 1
            pending_approvals = 0
            for item in self.items:
                for agent in item["agents"]:
                    if agent.get("pending_approval"):
                        pending_approvals += 1
            return {
                "topic": self.topic,
                "started_at": self.started_at,
                "last_rid": self.last_rid,
                "audit_log": self.audit_log,
                "target_override": self.target_override,
                "current_target": resolve_target(self.target_override, ""),
                "claude_sessions": list(self.claude_sessions),
                "latest_codex_session": self.latest_codex_session,
                "active_agents": active_agents,
                "pending_approvals": pending_approvals,
                "room_id": self.room_id,
                "room_state_path": self.room_state_path,
                "room_health": self.room_health,
                "recovery_reasons": list(self.recovery_reasons),
                "hardening": {
                    "transcript_sanitizer": self.hardening.transcript_sanitizer,
                    "version_gate": self.hardening.version_gate,
                    "version_gate_recheck": self.hardening.version_gate_recheck,
                    "operation_locks": self.hardening.operation_locks,
                    "external_audit_anchor": self.hardening.external_audit_anchor,
                    "remote_audit_publish": self.hardening.remote_anchor_publish,
                    "broker_recovery_mode": self.hardening.broker_recovery_mode,
                    "shared_host_collision_guard": self.hardening.shared_host_collision_guard,
                    "version_snapshots": copy.deepcopy(self.version_snapshots),
                    "version_gate_status": copy.deepcopy(self.version_gate),
                    "version_recheck_status": copy.deepcopy(self.version_recheck),
                    "degraded_features": copy.deepcopy(self.degraded_features),
                    "system_events": copy.deepcopy(self.system_events[-12:]),
                    "lock_snapshot": self.operation_locks.snapshot(),
                    "port_registry": self.port_registry.snapshot(),
                    "remote_anchor": copy.deepcopy(self.remote_anchor),
                },
                "items": copy.deepcopy(self.items),
            }

    def _mark_recovery_required(self, reason: str, *, feature: str = "broker_recovery") -> None:
        stamp = now_iso()
        with self.lock:
            if reason not in self.recovery_reasons:
                self.recovery_reasons.append(reason)
            self.room_health = "recovery_required"
            self.degraded_features[feature] = {
                "state": "recovery_required",
                "reason": reason,
                "updated_at": stamp,
            }

    def _refresh_room_health(self) -> None:
        with self.lock:
            if self.remote_anchor.get("state") == "read_only_diagnostic":
                self.room_health = "read_only_diagnostic"
            elif self.remote_anchor.get("state") == "anchor_blocked":
                self.room_health = "anchor_blocked"
            elif self.recovery_reasons:
                self.room_health = "recovery_required"
            elif self.remote_anchor.get("state") == "degraded" or self.degraded_features:
                self.room_health = "degraded"
            else:
                self.room_health = "healthy"

    def _serialize_room_state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "topic": self.topic,
                "room_id": self.room_id,
                "current_claude_session": self.current_claude_session,
                "latest_codex_session": self.latest_codex_session,
                "claude_sessions": list(self.claude_sessions),
                "claude_meeting_cursor": self.claude_meeting_cursor,
                "codex_meeting_cursor": self.codex_meeting_cursor,
                "target_override": self.target_override,
                "last_rid": self.last_rid,
                "room_health": self.room_health,
                "recovery_reasons": list(self.recovery_reasons),
                "remote_anchor": copy.deepcopy(self.remote_anchor),
                "degraded_features": copy.deepcopy(self.degraded_features),
                "system_events": copy.deepcopy(self.system_events[-50:]),
                "items": copy.deepcopy(self.items),
                "pending_approvals": [
                    {
                        "item_id": key[0],
                        "target": key[1],
                        "request_id": key[2],
                        "summary": (value["agent"].get("pending_approval") or {}).get("summary", ""),
                    }
                    for key, value in self.pending_approvals.items()
                ],
                "lock_snapshot": self.operation_locks.snapshot(),
                "port_registry": self.port_registry.snapshot(),
                "updated_at": now_iso(),
            }

    def _persist_room_state(self) -> None:
        self._refresh_room_health()
        atomic_write_json(self.room_state_path, self._serialize_room_state())

    def _load_persisted_broker_state(self) -> None:
        payload = dict(self.persisted_state or {})
        if not payload:
            return
        self.current_claude_session = payload.get("current_claude_session", "") or ""
        self.latest_codex_session = payload.get("latest_codex_session", "") or ""
        self.claude_sessions = list(payload.get("claude_sessions") or [])
        self.claude_meeting_cursor = int(payload.get("claude_meeting_cursor", 0) or 0)
        self.codex_meeting_cursor = int(payload.get("codex_meeting_cursor", 0) or 0)
        self.target_override = payload.get("target_override", "") or ""
        self.last_rid = payload.get("last_rid", "") or ""
        persisted_remote_anchor = dict(payload.get("remote_anchor") or {})
        merged_remote_anchor = copy.deepcopy(self.remote_anchor)
        merged_remote_anchor.update(persisted_remote_anchor)
        self.remote_anchor = merged_remote_anchor
        self.degraded_features = copy.deepcopy(payload.get("degraded_features") or {})
        self.system_events = copy.deepcopy(payload.get("system_events") or [])
        self.items = copy.deepcopy(payload.get("items") or [])
        orphaned_pending = list(payload.get("pending_approvals") or [])
        orphaned_locks = dict(payload.get("lock_snapshot") or {})
        unfinished = 0
        for item in self.items:
            for agent in item.get("agents", []):
                if agent.get("status") in {"queued", "running"} or agent.get("pending_approval"):
                    unfinished += 1
                    agent["status"] = "failed"
                    agent["confirmed"] = False
                    agent["pending_approval"] = None
                    agent["phase"] = "recovery_required"
                    agent["phase_label"] = "broker 重启后需要人工恢复"
                    agent["next_step"] = "请人工确认状态并重新发起本轮"
                    agent["current_detail"] = "broker 在该 agent 完成前重启"
                    self.append_event(agent, "failed", "broker restart interrupted this agent")
        if orphaned_pending:
            self._mark_recovery_required(f"orphaned approvals recovered: {len(orphaned_pending)}")
        if orphaned_locks:
            self._mark_recovery_required(f"orphaned lock snapshot recovered: {len(orphaned_locks)}")
        if unfinished:
            self._mark_recovery_required(f"incomplete agents recovered: {unfinished}")

    def _recover_port_registry(self) -> None:
        for event in self.port_registry.reconcile_after_restart():
            detail = f"port {event.get('port')} {event.get('kind')}"
            self.emit_system_event(
                event.get("kind", "port_registry_event"),
                detail,
                severity="warn",
                feature="shared_host_collision_guard",
            )

    def reset_recovery(self) -> tuple[bool, str]:
        with self.lock:
            if self.pending_approvals:
                return False, "pending approvals still exist"
            active = any(
                agent.get("status") in {"queued", "running"}
                for item in self.items
                for agent in item.get("agents", [])
            )
            if active:
                return False, "active agents still running"
            if self.remote_anchor.get("state") == "read_only_diagnostic":
                if self.remote_anchor.get("verify_status") != "verified":
                    return False, "remote verifier has not passed yet"
                self.remote_anchor["state"] = "healthy"
                self.remote_anchor["last_reason"] = ""
                self.remote_anchor["recovery_verify_ready"] = False
                self.degraded_features.pop("remote_anchor", None)
                self.recovery_reasons = []
                self.degraded_features.pop("broker_recovery", None)
                self._persist_room_state()
                self.broadcast()
                return True, ""
            if self.remote_anchor.get("state") == "anchor_blocked":
                if not self.remote_anchor.get("recovery_publish_ready"):
                    return False, "remote anchor publish recovery has not completed yet"
                if not self.remote_anchor.get("recovery_verify_ready"):
                    return False, "remote verifier has not passed yet"
                if self.remote_anchor.get("last_status") != "published" or int(self.remote_anchor.get("backlog_count", 0) or 0) > 0:
                    return False, "remote anchor has not recovered yet"
                self.remote_anchor["state"] = "healthy"
                self.remote_anchor["consecutive_unanchored"] = 0
                self.remote_anchor["last_reason"] = ""
                self.remote_anchor["recovery_publish_ready"] = False
                self.remote_anchor["recovery_verify_ready"] = False
                self.degraded_features.pop("remote_anchor", None)
            self.recovery_reasons = []
            self.degraded_features.pop("broker_recovery", None)
        self._persist_room_state()
        self.broadcast()
        return True, ""

    def _update_remote_anchor_state(self, record: dict[str, Any]) -> None:
        policy = record.get("remote_anchor_policy") or self.hardening.remote_anchor_publish
        status = record.get("remote_anchor_status") or ("disabled" if policy == "disabled" else "unknown")
        reason = record.get("remote_anchor_reason", "") or ""
        backlog_count = int(record.get("remote_anchor_backlog_count", 0) or 0)
        hard_cap_exceeded = bool(record.get("remote_anchor_hard_cap_exceeded"))
        remote_sequence = record.get("remote_anchor_remote_sequence")
        with self.lock:
            self.remote_anchor["policy"] = policy
            self.remote_anchor["last_status"] = status
            self.remote_anchor["last_reason"] = reason
            self.remote_anchor["backlog_count"] = backlog_count
            self.remote_anchor["last_remote_sequence"] = remote_sequence
            self.remote_anchor["updated_at"] = now_iso()
            if policy == "disabled":
                self.remote_anchor["state"] = "disabled"
                self.remote_anchor["consecutive_unanchored"] = 0
                self.remote_anchor["recovery_publish_ready"] = False
                self.degraded_features.pop("remote_anchor", None)
                return
            if status == "published":
                self.remote_anchor["consecutive_unanchored"] = 0
                if self.remote_anchor.get("state") == "anchor_blocked":
                    self.remote_anchor["recovery_publish_ready"] = True
                if self.remote_anchor.get("state") == "anchor_blocked":
                    self.degraded_features["remote_anchor"] = {
                        "state": "anchor_blocked",
                        "reason": "remote anchor recovered; awaiting operator reset",
                        "updated_at": self.remote_anchor["updated_at"],
                    }
                    return
                if backlog_count == 0:
                    self.remote_anchor["state"] = "healthy"
                    self.degraded_features.pop("remote_anchor", None)
                else:
                    self.remote_anchor["state"] = "degraded"
                    self.degraded_features["remote_anchor"] = {
                        "state": "degraded",
                        "reason": f"remote anchor backlog pending: {backlog_count}",
                        "updated_at": self.remote_anchor["updated_at"],
                    }
                return

            self.remote_anchor["consecutive_unanchored"] = int(self.remote_anchor.get("consecutive_unanchored", 0) or 0) + 1
            self.remote_anchor["recovery_publish_ready"] = False
            if hard_cap_exceeded or (policy == "blocking" and self.remote_anchor["consecutive_unanchored"] >= 3):
                self.remote_anchor["state"] = "anchor_blocked"
                self.degraded_features["remote_anchor"] = {
                    "state": "anchor_blocked",
                    "reason": reason or (
                        f"remote anchor backlog hard cap exceeded ({backlog_count})"
                        if hard_cap_exceeded
                        else f"remote anchor blocked after {self.remote_anchor['consecutive_unanchored']} unanchored turns"
                    ),
                    "updated_at": self.remote_anchor["updated_at"],
                }
            else:
                self.remote_anchor["state"] = "degraded"
                self.degraded_features["remote_anchor"] = {
                    "state": "degraded",
                    "reason": reason or "remote anchor publish degraded",
                    "updated_at": self.remote_anchor["updated_at"],
                }

    def _apply_remote_verifier_result(self, result: dict[str, Any], *, trigger: str) -> None:
        policy = result.get("policy", self.hardening.remote_anchor_publish)
        verify_result = result.get("result", "disabled")
        reason = result.get("reason", "") or ""
        now = now_iso()
        with self.lock:
            self.remote_anchor["verify_status"] = verify_result
            self.remote_anchor["verify_reason"] = reason
            self.remote_anchor["verify_checked_local"] = int(result.get("checked_local", 0) or 0)
            self.remote_anchor["verify_checked_remote"] = int(result.get("checked_remote", 0) or 0)
            self.remote_anchor["verify_last_sequence"] = result.get("latest_remote_sequence")
            self.remote_anchor["verify_last_trigger"] = trigger
            self.remote_anchor["verify_last_checked_at"] = now
            self.remote_anchor["updated_at"] = now
            self.remote_anchor["verifier_running"] = False

            if verify_result == "disabled":
                return

            if verify_result == "verified":
                self.remote_anchor["recovery_verify_ready"] = self.remote_anchor.get("state") in {"anchor_blocked", "read_only_diagnostic"}
                if self.remote_anchor.get("state") == "read_only_diagnostic":
                    self.degraded_features["remote_anchor"] = {
                        "state": "read_only_diagnostic",
                        "reason": "remote verifier recovered; awaiting operator reset",
                        "updated_at": now,
                    }
                    return
                if self.remote_anchor.get("state") == "anchor_blocked":
                    publish_ready = bool(self.remote_anchor.get("recovery_publish_ready"))
                    detail = "remote anchor recovered; awaiting operator reset" if publish_ready else "remote verifier recovered; awaiting publish recovery"
                    self.degraded_features["remote_anchor"] = {
                        "state": "anchor_blocked",
                        "reason": detail,
                        "updated_at": now,
                    }
                    return
                if self.remote_anchor.get("backlog_count", 0):
                    self.remote_anchor["state"] = "degraded"
                    self.degraded_features["remote_anchor"] = {
                        "state": "degraded",
                        "reason": f"remote anchor backlog pending: {self.remote_anchor['backlog_count']}",
                        "updated_at": now,
                    }
                else:
                    self.remote_anchor["state"] = "healthy"
                    self.degraded_features.pop("remote_anchor", None)
                return

            self.remote_anchor["recovery_verify_ready"] = False
            if verify_result == "mismatch":
                if trigger == "startup":
                    self.remote_anchor["state"] = "read_only_diagnostic"
                    self.degraded_features["remote_anchor"] = {
                        "state": "read_only_diagnostic",
                        "reason": reason or "startup remote verifier mismatch",
                        "updated_at": now,
                    }
                else:
                    self.remote_anchor["state"] = "anchor_blocked"
                    self.degraded_features["remote_anchor"] = {
                        "state": "anchor_blocked",
                        "reason": reason or "remote verifier mismatch",
                        "updated_at": now,
                    }
                return

            if verify_result == "unreachable":
                if policy == "blocking":
                    self.remote_anchor["state"] = "anchor_blocked"
                    self.degraded_features["remote_anchor"] = {
                        "state": "anchor_blocked",
                        "reason": reason or "remote verifier transport failure",
                        "updated_at": now,
                    }
                else:
                    self.remote_anchor["state"] = "degraded"
                    self.degraded_features["remote_anchor"] = {
                        "state": "degraded",
                        "reason": reason or "remote verifier transport failure",
                        "updated_at": now,
                    }

    def _run_remote_verifier(self, *, trigger: str, asynchronous: bool) -> dict[str, Any] | None:
        if self.hardening.remote_anchor_publish == "disabled":
            with self.lock:
                self.remote_anchor["verify_status"] = "disabled"
                self.remote_anchor["verify_last_trigger"] = trigger
            return {"policy": "disabled", "result": "disabled"}

        if asynchronous:
            with self.lock:
                if self.remote_anchor.get("verifier_running"):
                    return None
                self.remote_anchor["verifier_running"] = True
            worker = threading.Thread(target=self._run_remote_verifier, kwargs={"trigger": trigger, "asynchronous": False}, daemon=True)
            worker.start()
            return None

        with self.remote_verify_lock:
            with self.lock:
                self.remote_anchor["verifier_running"] = True
                expected_backlog = int(self.remote_anchor.get("backlog_count", 0) or 0)
            try:
                result = verify_remote_anchor(
                    self.hardening,
                    room_id=self.room_id,
                    expected_backlog_count=expected_backlog,
                )
            except Exception as exc:  # noqa: BLE001
                result = {
                    "policy": self.hardening.remote_anchor_publish,
                    "result": "unreachable",
                    "ok": False,
                    "reason": f"verifier exception: {exc}",
                    "room_id": self.room_id,
                    "checked_local": 0,
                    "checked_remote": 0,
                    "latest_remote_sequence": None,
                    "mismatch_kind": "",
                    "transport_failure": True,
                }
            self._apply_remote_verifier_result(result, trigger=trigger)
            severity = "info"
            if result.get("result") == "verified":
                kind = "remote_verifier_ok"
                detail = f"remote verifier passed ({trigger})"
            elif result.get("result") == "disabled":
                kind = "remote_verifier_disabled"
                detail = "remote verifier disabled"
            elif result.get("result") == "unreachable":
                kind = "remote_verifier_unreachable"
                detail = result.get("reason", "remote verifier unreachable")
                severity = "warn" if self.hardening.remote_anchor_publish == "async" else "error"
            else:
                kind = "remote_verifier_mismatch"
                detail = result.get("reason", "remote verifier mismatch")
                severity = "error"
            self.emit_system_event(kind, detail, severity=severity, feature="")
            self._persist_room_state()
            self.broadcast()
            return result

    def _maybe_schedule_remote_verifier(self) -> None:
        if self.hardening.remote_anchor_publish == "disabled":
            return
        should_run = False
        with self.lock:
            self.remote_anchor["verify_turn_counter"] = int(self.remote_anchor.get("verify_turn_counter", 0) or 0) + 1
            interval = max(1, min(50, int(self.hardening.remote_anchor_verify_interval_turns)))
            last_turn = int(self.remote_anchor.get("verify_last_turn", 0) or 0)
            current_turn = int(self.remote_anchor["verify_turn_counter"])
            if current_turn - last_turn >= interval and not self.remote_anchor.get("verifier_running"):
                self.remote_anchor["verify_last_turn"] = current_turn
                should_run = True
        if should_run:
            self._run_remote_verifier(trigger="periodic", asynchronous=True)

    def emit_system_event(self, kind: str, detail: str, *, severity: str = "info", feature: str = "") -> None:
        event = {
            "ts": now_iso(),
            "kind": kind,
            "severity": severity,
            "detail": detail,
            "feature": feature,
        }
        with self.lock:
            self.system_events.append(event)
            self.system_events = self.system_events[-100:]
            if feature and severity in {"warn", "error"}:
                self.degraded_features[feature] = {
                    "state": "degraded",
                    "reason": detail,
                    "updated_at": event["ts"],
                }
        append_hardening_event(
            self.hardening.alert_log_path,
            {
                "timestamp": event["ts"],
                "kind": kind,
                "severity": severity,
                "detail": detail,
                "feature": feature,
                "source": "broker",
                "room_id": self.room_id,
            },
        )
        self._persist_room_state()

    def register_client(self, sock: socket.socket) -> None:
        with self.lock:
            self.clients.add(sock)

    def unregister_client(self, sock: socket.socket) -> None:
        with self.lock:
            self.clients.discard(sock)

    def broadcast(self) -> None:
        payload = json.dumps({"type": "state", "state": self.snapshot()}, ensure_ascii=False)
        dead = []
        with self.lock:
            clients = list(self.clients)
        for sock in clients:
            try:
                send_ws_text(sock, payload)
            except OSError:
                dead.append(sock)
        for sock in dead:
            self.unregister_client(sock)

    def append_event(self, agent: dict[str, Any], status: str, detail: str) -> None:
        agent["events"].append(
            {
                "ts": now_iso(),
                "status": status,
                "label": status_label(status, agent.get("confirmed")),
                "detail": detail,
            }
        )
        agent["events"] = agent["events"][-MAX_AGENT_EVENTS:]

    def _set_agent_phase(
        self,
        agent: dict[str, Any],
        phase: str,
        phase_label: str,
        next_step: str,
        current_detail: str,
        event_detail: str | None = None,
        *,
        broadcast: bool = True,
    ) -> None:
        with self.lock:
            agent["phase"] = phase
            agent["phase_label"] = phase_label
            agent["next_step"] = next_step
            agent["current_detail"] = current_detail
            if event_detail:
                self.append_event(agent, "running", event_detail)
        if broadcast:
            self.broadcast()

    def _parse_codex_stderr_event(self, line: str) -> dict[str, str] | None:
        text = line.strip()
        if not text:
            return None
        if text.startswith("OpenAI Codex v"):
            return {
                "phase": "cli_started",
                "phase_label": "Codex CLI 已启动",
                "next_step": "等待工作区和上下文日志",
                "current_detail": text,
                "event_detail": text,
            }
        if text.startswith("workdir:"):
            return {
                "phase": "context_scan",
                "phase_label": "正在读取工作区上下文",
                "next_step": "继续观察上下文文件与内部命令",
                "current_detail": text,
                "event_detail": f"已进入工作目录：{text.split(':', 1)[1].strip()}",
            }
        if text.startswith("mcp startup:"):
            return {
                "phase": "context_scan",
                "phase_label": "正在准备执行环境",
                "next_step": "等待工作区扫描与命令执行",
                "current_detail": text,
                "event_detail": text,
            }
        if text in {"user", "codex"}:
            return None
        if text.startswith("/bin/") or text.startswith("/usr/bin/"):
            phase_label = "正在执行工作区命令"
            next_step = "等待命令输出并继续推进"
            event_detail = f"开始执行：{shorten_command(text)}"
            if any(marker in text for marker in ("SOUL.md", "USER.md", "MEMORY.md", "memory/")):
                phase_label = "正在读取启动上下文"
                next_step = "等待上下文读取完成后继续处理请求"
                event_detail = f"开始读取上下文：{shorten_command(text)}"
            return {
                "phase": "exec_running",
                "phase_label": phase_label,
                "next_step": next_step,
                "current_detail": shorten_command(text),
                "event_detail": event_detail,
            }
        if "succeeded in " in text or "exited " in text:
            return {
                "phase": "exec_running",
                "phase_label": "工作区命令已返回",
                "next_step": "继续等待 Codex 生成最终回复",
                "current_detail": shorten_command(text),
                "event_detail": shorten_command(text),
            }
        if text.startswith("PermissionError:"):
            return {
                "phase": "exec_running",
                "phase_label": "内部命令碰到受限操作",
                "next_step": "CLI 仍在继续执行，等待后续结果",
                "current_detail": text,
                "event_detail": "内部命令碰到受限操作；CLI 继续运行",
            }
        if text.startswith("Traceback (most recent call last):"):
            return None
        if text.startswith("tokens used"):
            return {
                "phase": "finalizing",
                "phase_label": "正在回传最终结果",
                "next_step": "等待审计确认和 session 绑定",
                "current_detail": text,
                "event_detail": text,
            }
        if text.startswith("model:") or text.startswith("provider:") or text.startswith("approval:") or text.startswith("sandbox:") or text.startswith("reasoning "):
            return {
                "phase": "context_scan",
                "phase_label": "正在初始化执行配置",
                "next_step": "等待工作区扫描与内部命令",
                "current_detail": text,
                "event_detail": text,
            }
        return None

    def _append_claude_session(self, session_id: str) -> None:
        if session_id and (not self.claude_sessions or self.claude_sessions[-1] != session_id):
            self.claude_sessions.append(session_id)
            self.claude_sessions = self.claude_sessions[-MAX_CLAUDE_HISTORY:]

    def _infer_raw_text(self, targets: list[str], message_body: str) -> str:
        if targets == ["claude", "codex"]:
            return f"@all {message_body}".strip()
        if targets == ["claude"]:
            return f"@claude {message_body}".strip()
        if targets == ["codex"]:
            return f"@codex {message_body}".strip()
        return message_body

    def _build_meeting_entries(self) -> list[dict[str, str]]:
        entries = []
        with self.lock:
            items = copy.deepcopy(self.items)

        for item in sorted(items, key=lambda x: x.get("created_at", "")):
            if item.get("source") == "system":
                continue
            raw_text = (item.get("raw_text") or "").strip()
            if raw_text:
                entries.append({"speaker": "User", "text": raw_text})
            for agent in item.get("agents", []):
                reply = (agent.get("reply") or "").strip()
                if reply:
                    entries.append({"speaker": agent.get("label", "Agent"), "text": reply})
        return entries

    def _agent_from_record(self, record: dict[str, Any]) -> dict[str, Any]:
        target = record.get("target", "unknown")
        confirmed = bool(record.get("session_confirmed"))
        reply = (record.get("stdout") or "").strip()
        if not reply:
            stderr = (record.get("stderr") or "").strip()
            reply = stderr or "(无输出)"

        meta = dict(record.get("verify_commands") or {})
        meta.update(
            {
                "rid": record.get("rid", ""),
                "nonce": record.get("nonce", ""),
                "session_id": record.get("session_id", ""),
                "session_file": record.get("session_file", ""),
                "confirmation_method": record.get("confirmation_method", ""),
                "confirmation": record.get("confirmation", {}),
                "exit_code": record.get("exit_code"),
                "summary_chain_path": record.get("summary_chain_path", ""),
                "prev_summary_sha256": record.get("prev_summary_sha256", ""),
                "turn_summary_sha256": record.get("turn_summary_sha256", ""),
                "summary_chain_genesis_sha256": record.get("summary_chain_genesis_sha256", ""),
                "external_anchor_policy": record.get("external_anchor_policy", ""),
                "external_anchor_status": record.get("external_anchor_status", ""),
                "external_anchor_bundle_path": record.get("external_anchor_bundle_path", ""),
                "external_anchor_reason": record.get("external_anchor_reason", ""),
                "remote_anchor_policy": record.get("remote_anchor_policy", ""),
                "remote_anchor_status": record.get("remote_anchor_status", ""),
                "remote_anchor_reason": record.get("remote_anchor_reason", ""),
                "remote_anchor_backlog_path": record.get("remote_anchor_backlog_path", ""),
                "remote_anchor_backlog_count": record.get("remote_anchor_backlog_count", 0),
                "remote_anchor_drained_count": record.get("remote_anchor_drained_count", 0),
                "remote_anchor_remote_sequence": record.get("remote_anchor_remote_sequence"),
                "remote_anchor_remote_record_id": record.get("remote_anchor_remote_record_id", ""),
                "remote_anchor_hard_cap_exceeded": record.get("remote_anchor_hard_cap_exceeded", False),
                "remote_anchor_current_published": record.get("remote_anchor_current_published", False),
            }
        )

        timestamp = record.get("timestamp", now_iso())
        phase_label = (
            "历史记录（审计日志显示已验真）"
            if confirmed
            else "历史记录（审计日志显示未验真）"
        )
        agent = {
            "target": target,
            "label": "Claude" if target == "claude" else "Codex",
            "status": "done",
            "confirmed": confirmed,
            "created_at": timestamp,
            "started_at": timestamp,
            "finished_at": timestamp,
            "phase": "history",
            "phase_label": phase_label,
            "next_step": "可复制 verify-rid / resume 继续复核",
            "current_detail": "这是一条从 audit.jsonl 恢复的历史记录",
            "reply": reply,
            "meta": meta,
            "events": [],
            "pending_approval": None,
        }
        self.append_event(agent, "done", "从 audit.jsonl 恢复")
        return agent

    def _load_history(self) -> None:
        if not os.path.isfile(self.audit_log):
            return

        grouped: dict[str, list[dict[str, Any]]] = {}
        try:
            with open(self.audit_log, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rid = record.get("rid") or ""
                    if rid:
                        grouped.setdefault(rid, []).append(record)
        except OSError:
            return

        recovered = []
        for rid, records in grouped.items():
            latest_by_target = {}
            for record in records:
                latest_by_target[record.get("target", "unknown")] = record

            targets = [t for t in ("claude", "codex") if t in latest_by_target]
            if not targets:
                continue

            first = min(records, key=lambda rec: rec.get("timestamp", ""))
            agents = [self._agent_from_record(latest_by_target[target]) for target in targets]
            recovered.append(
                {
                    "id": f"audit-{rid}",
                    "source": "audit_replay",
                    "raw_text": self._infer_raw_text(targets, first.get("message_body", "")),
                    "message": first.get("message_body", ""),
                    "targets": targets,
                    "rid": rid,
                    "nonce": first.get("nonce", ""),
                    "target_name": first.get("target_name", "meeting"),
                    "target_source": first.get("target_source", "default"),
                    "target_path": first.get("target_path", ""),
                    "created_at": first.get("timestamp", now_iso()),
                    "agents": agents,
                }
            )

        recovered.sort(key=lambda item: item["created_at"])
        with self.lock:
            existing_rids = {item.get("rid", "") for item in self.items if item.get("rid")}
            for item in recovered:
                if item.get("rid") and item["rid"] in existing_rids:
                    continue
                self.items.append(item)
                self.last_rid = item["rid"]
                for agent in item["agents"]:
                    session_id = agent["meta"].get("session_id", "")
                    if agent["target"] == "claude":
                        self._append_claude_session(session_id)
                    elif agent["target"] == "codex" and session_id:
                        self.latest_codex_session = session_id
            self.items.sort(key=lambda x: x["created_at"])

    def _find_item_by_rid(self, rid: str) -> dict[str, Any] | None:
        for item in self.items:
            if item.get("rid") == rid:
                return item
        return None

    def _merge_audit_record(self, record: dict[str, Any]) -> bool:
        rid = record.get("rid") or ""
        target = record.get("target") or ""
        if not rid or target not in ("claude", "codex"):
            return False

        with self.lock:
            item = self._find_item_by_rid(rid)
            if item is None:
                item = {
                    "id": f"audit-live-{rid}",
                    "source": "audit_live",
                    "raw_text": self._infer_raw_text([target], record.get("message_body", "")),
                    "message": record.get("message_body", ""),
                    "targets": [target],
                    "rid": rid,
                    "nonce": record.get("nonce", ""),
                    "target_name": record.get("target_name", "meeting"),
                    "target_source": record.get("target_source", "default"),
                    "target_path": record.get("target_path", ""),
                    "created_at": record.get("timestamp", now_iso()),
                    "agents": [],
                }
                self.items.append(item)
                self.items.sort(key=lambda x: x["created_at"])

            if target not in item["targets"]:
                item["targets"] = sorted(item["targets"] + [target])
                item["raw_text"] = self._infer_raw_text(item["targets"], item.get("message", ""))
            item["target_name"] = record.get("target_name", item.get("target_name", "meeting"))
            item["target_source"] = record.get("target_source", item.get("target_source", "default"))
            item["target_path"] = record.get("target_path", item.get("target_path", ""))

            agent = next((a for a in item["agents"] if a["target"] == target), None)
            if agent is None:
                agent = self._agent_from_record(record)
                item["agents"].append(agent)
            else:
                confirmed = bool(record.get("session_confirmed"))
                reply = (record.get("stdout") or "").strip()
                if not reply:
                    stderr = (record.get("stderr") or "").strip()
                    reply = stderr or "(无输出)"
                meta = dict(record.get("verify_commands") or {})
                meta.update(
                    {
                        "rid": record.get("rid", ""),
                        "nonce": record.get("nonce", ""),
                        "session_id": record.get("session_id", ""),
                        "session_file": record.get("session_file", ""),
                        "confirmation_method": record.get("confirmation_method", ""),
                        "confirmation": record.get("confirmation", {}),
                        "exit_code": record.get("exit_code"),
                        "summary_chain_path": record.get("summary_chain_path", ""),
                        "prev_summary_sha256": record.get("prev_summary_sha256", ""),
                        "turn_summary_sha256": record.get("turn_summary_sha256", ""),
                        "summary_chain_genesis_sha256": record.get("summary_chain_genesis_sha256", ""),
                        "external_anchor_policy": record.get("external_anchor_policy", ""),
                        "external_anchor_status": record.get("external_anchor_status", ""),
                        "external_anchor_bundle_path": record.get("external_anchor_bundle_path", ""),
                        "external_anchor_reason": record.get("external_anchor_reason", ""),
                        "remote_anchor_policy": record.get("remote_anchor_policy", ""),
                        "remote_anchor_status": record.get("remote_anchor_status", ""),
                        "remote_anchor_reason": record.get("remote_anchor_reason", ""),
                        "remote_anchor_backlog_path": record.get("remote_anchor_backlog_path", ""),
                        "remote_anchor_backlog_count": record.get("remote_anchor_backlog_count", 0),
                        "remote_anchor_drained_count": record.get("remote_anchor_drained_count", 0),
                        "remote_anchor_remote_sequence": record.get("remote_anchor_remote_sequence"),
                        "remote_anchor_remote_record_id": record.get("remote_anchor_remote_record_id", ""),
                        "remote_anchor_hard_cap_exceeded": record.get("remote_anchor_hard_cap_exceeded", False),
                        "remote_anchor_current_published": record.get("remote_anchor_current_published", False),
                    }
                )
                agent["reply"] = reply
                agent["meta"] = meta
                agent["confirmed"] = confirmed
                agent["status"] = "done"
                agent["phase"] = "done"
                agent["phase_label"] = "已完成并验真" if confirmed else "已完成，等待人工复核"
                agent["next_step"] = (
                    "可复制 verify-rid / resume 继续复核"
                    if confirmed
                    else "建议展开审计信息，按 verify-rid 做人工复核"
                )
                agent["current_detail"] = "已从 audit.jsonl 合并权威记录"
                agent["finished_at"] = record.get("timestamp", now_iso())
                agent["pending_approval"] = None
                self.append_event(agent, "done", "已从 audit.jsonl 合并权威记录")

            self.last_rid = rid
            session_id = record.get("session_id", "")
            if target == "claude" and session_id:
                self._append_claude_session(session_id)
                if record.get("exit_code") == 0:
                    self.current_claude_session = session_id
            elif target == "codex" and session_id:
                self.latest_codex_session = session_id
        self._update_remote_anchor_state(record)
        self._persist_room_state()
        self._maybe_schedule_remote_verifier()
        return True

    def _tail_audit_log(self) -> None:
        while True:
            try:
                if not os.path.isfile(self.audit_log):
                    time.sleep(0.5)
                    continue
                file_size = os.path.getsize(self.audit_log)
                if file_size < self.audit_offset:
                    self.audit_offset = 0
                changed = False
                with open(self.audit_log, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(self.audit_offset)
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if self._merge_audit_record(record):
                            changed = True
                    self.audit_offset = f.tell()
                if changed:
                    self.broadcast()
            except OSError:
                pass
            time.sleep(0.5)

    def submit(self, raw_text: str) -> dict[str, Any]:
        raw_text = raw_text.strip()
        target_cmd = parse_target_command(raw_text)
        if target_cmd:
            return self._handle_target_command(raw_text, target_cmd)
        if self.room_health == "read_only_diagnostic":
            raise ValueError("远端审计锚处于只读诊断态，拒绝新的 turn；请先运行 verifier 并确认恢复")
        if self.room_health == "anchor_blocked":
            raise ValueError("远端审计锚当前阻断中，拒绝新的 turn；请先处理 anchor_blocked 状态")

        targets, message = parse_message(raw_text)
        if not targets:
            raise ValueError("请使用 @claude / @codex / @all 指定目标")
        if not message:
            raise ValueError("消息不能为空")

        audit_msg = build_audit_message(message)
        target_info = resolve_target(self.target_override, message)
        item_id = secrets.token_hex(8)
        agents = []
        for target in targets:
            label = "Claude" if target == "claude" else "Codex"
            agent = {
                "target": target,
                "label": label,
                "status": "queued",
                "confirmed": None,
                "created_at": now_iso(),
                "started_at": "",
                "finished_at": "",
                "phase": "queued",
                "phase_label": "等待启动",
                "next_step": "等待进入本地执行队列",
                "current_detail": "请求已进入本地队列",
                "reply": "",
                "meta": {},
                "hardening": {},
                "events": [],
                "pending_approval": None,
                "held_lock_owners": [],
            }
            self.append_event(agent, "queued", "等待本地执行队列")
            agents.append(agent)

        item = {
            "id": item_id,
            "source": "live",
            "raw_text": raw_text,
            "message": message,
            "targets": targets,
            "rid": audit_msg["rid"],
            "nonce": audit_msg["nonce"],
            "target_name": target_info["name"],
            "target_source": target_info["source"],
            "target_path": target_info.get("repo_path", ""),
            "created_at": now_iso(),
            "agents": agents,
        }

        with self.lock:
            self.items.append(item)
            self.last_rid = audit_msg["rid"]
        self._persist_room_state()
        self.broadcast()

        worker = threading.Thread(
            target=self._run_item,
            args=(item_id, audit_msg["wrapped_message"], target_info),
            daemon=True,
        )
        worker.start()
        return item

    def _handle_target_command(self, raw_text: str, target_cmd: dict[str, str]) -> dict[str, Any]:
        if target_cmd["action"] == "status":
            target_info = resolve_target(self.target_override, "")
            text = f"当前 target: {target_info['name']} ({target_info['source']})"
            if target_info.get("repo_path"):
                text += f"\n目标路径: {target_info['repo_path']}"
        elif target_cmd["action"] == "set":
            self.target_override = target_cmd["value"]
            target_info = resolve_target(self.target_override, "")
            mode = "自动" if not self.target_override else "显式"
            text = f"已切换 target: {target_info['name']} ({mode})"
            if target_info.get("repo_path"):
                text += f"\n目标路径: {target_info['repo_path']}"
        else:
            text = "无效 target。可用值: meeting / polaris / auto / status"
            target_info = resolve_target(self.target_override, "")

        item = {
            "id": secrets.token_hex(8),
            "source": "system",
            "raw_text": raw_text,
            "message": text,
            "targets": [],
            "rid": "",
            "nonce": "",
            "target_name": target_info["name"],
            "target_source": target_info["source"],
            "target_path": target_info.get("repo_path", ""),
            "created_at": now_iso(),
            "agents": [],
        }
        with self.lock:
            self.items.append(item)
        self._persist_room_state()
        self.broadcast()
        return item

    def _release_agent_locks(self, agent: dict[str, Any]) -> None:
        held = list(agent.get("held_lock_owners") or [])
        for owner in held:
            self.operation_locks.release_owner(owner)
            self.port_registry.release_owner(owner)
        if held:
            agent["held_lock_owners"] = []
            self._persist_room_state()

    def _run_item(self, item_id: str, wrapped_message: str, target_info: dict[str, Any]) -> None:
        with self.lock:
            item = next((x for x in self.items if x["id"] == item_id), None)
        if not item:
            return

        for agent in list(item["agents"]):
            self._run_agent(item, agent, wrapped_message, target_info)

    def _run_agent(self, item: dict[str, Any], agent: dict[str, Any], wrapped_message: str, target_info: dict[str, Any]) -> None:
            target = agent["target"]
            label = agent["label"]
            gate = self.version_gate.get(target, {"allowed": True, "matched": True, "policy": "disabled", "reason": ""})
            with self.lock:
                agent["status"] = "running"
                agent["started_at"] = now_iso()
                agent["phase"] = "waiting_cli"
                agent["phase_label"] = "等待 agent CLI 返回"
                agent["next_step"] = "CLI 返回后将进入 session 验证与结果整理"
                agent["current_detail"] = f"{label} 已提交给 launcher"
                self.append_event(agent, "running", f"{label} 已提交给 launcher，正在等待 CLI + 审计完成")
            self.broadcast()

            if not gate.get("allowed", True):
                with self.lock:
                    agent["status"] = "failed"
                    agent["reply"] = f"[Hardening] blocked by version gate: {gate.get('reason', 'unknown')}"
                    agent["hardening"] = {"version_gate": gate}
                    self.append_event(agent, "failed", agent["reply"])
                self.emit_system_event(
                    "version_gate_block",
                    f"{label} blocked by version gate: {gate.get('reason', 'unknown')}",
                    severity="error",
                    feature="version_gate",
                )
                self.broadcast()
                return
            if not gate.get("matched", True) and gate.get("policy") == "warn":
                self.emit_system_event(
                    "version_gate_warn",
                    f"{label} is outside allowlist: {gate.get('reason', 'unknown')}",
                    severity="warn",
                    feature="version_gate",
                )
            invocation_snapshot = snapshot_runner_version(
                target,
                self.conf,
                settings=self.hardening,
                previous_snapshot=self.version_recheck_snapshots.get(target),
            )
            recheck = evaluate_version_recheck(
                target,
                self.version_snapshots[target],
                invocation_snapshot,
                settings=self.hardening,
            )
            self.version_recheck_snapshots[target] = invocation_snapshot
            self.version_recheck[target] = recheck
            if not recheck.get("allowed", True):
                with self.lock:
                    agent["status"] = "failed"
                    agent["reply"] = f"[Hardening] blocked by version recheck: {recheck.get('reason', 'unknown')}"
                    agent["hardening"] = {"version_gate": gate, "version_recheck": recheck}
                    self.append_event(agent, "failed", agent["reply"])
                self.emit_system_event(
                    "version_recheck_block",
                    f"{label} blocked by version recheck: {recheck.get('reason', 'unknown')}",
                    severity="error",
                    feature="version_gate",
                )
                self.broadcast()
                return
            if recheck.get("result") in {"changed-and-unapproved", "missing"} and recheck.get("policy") == "warn":
                self.emit_system_event(
                    "version_recheck_warn",
                    f"{label} invocation drift: {recheck.get('reason', 'unknown')}",
                    severity="warn",
                    feature="version_gate",
                )
            elif recheck.get("result") == "changed-but-allowed":
                self.emit_system_event(
                    "version_recheck_change",
                    f"{label} runner changed but still matches allowlist",
                    severity="info",
                    feature="version_gate",
                )

            if target == "claude":
                session_id = self.current_claude_session or str(uuid.uuid4())
                resume_session = bool(self.current_claude_session)
            else:
                session_id = ""
                resume_session = False
            agent_target_info = resolve_agent_target_info(target, target_info, self.conf)

            # 记忆注入：只读自己的事实层记忆
            # 持久 session 下，记忆只在首轮注入（后续轮 session 历史已包含）
            with self.lock:
                is_persistent = (target == "claude" and resume_session) or (target == "codex" and self.codex_runner_enabled)
                memory_cursor = self.claude_meeting_cursor if target == "claude" else self.codex_meeting_cursor
                skip_memory = is_persistent and memory_cursor > 0
            if target == "codex" and self.codex_runner_enabled:
                mem = {
                    "injected": False,
                    "profile": "runner_managed",
                    "files": [],
                    "source_files": [],
                    "sha256": "",
                    "bytes": 0,
                    "text": "",
                    "mirror_generated_at": "",
                }
                injected_message = wrapped_message
            elif skip_memory:
                mem = {
                    "injected": False,
                    "profile": "skipped_persistent_session",
                    "files": [],
                    "source_files": [],
                    "sha256": "",
                    "bytes": 0,
                    "text": "",
                    "mirror_generated_at": "",
                }
                injected_message = wrapped_message
            else:
                mem = load_memory(target, target_name=agent_target_info.get("name", "meeting"))
                injected_message = build_injected_message(mem, wrapped_message)
            injected_message = build_target_message(agent_target_info, injected_message)
            # 持久 session 下只注入增量会议上下文，避免双重历史
            since = memory_cursor if is_persistent else 0
            meeting_entries = self._build_meeting_entries()
            injected_message, next_cursor, meeting_mode, sanitizer_meta = build_meeting_context(meeting_entries, injected_message, since_index=since)
            cwd_override = target_info.get("claude_cwd") if target == "claude" else None
            with self.lock:
                agent["memory"] = {
                    "injected": mem["injected"],
                    "profile": mem["profile"],
                    "files": mem["files"],
                    "source_files": mem.get("source_files", []),
                    "sha256": mem["sha256"],
                    "bytes": mem["bytes"],
                    "mirror_generated_at": mem.get("mirror_generated_at", ""),
                }
                if mem["injected"]:
                    self.append_event(
                        agent, "running",
                        f"记忆注入: {mem['profile']} ({len(mem['files'])} 文件, {mem['bytes']} 字节)"
                    )
                if agent_target_info.get("injected"):
                    self.append_event(
                        agent, "running",
                        f"目标上下文: {agent_target_info['name']} ({agent_target_info['source']})"
                    )
                agent["hardening"] = {
                    "version_gate": gate,
                    "version_recheck": recheck,
                    "sanitizer": sanitizer_meta,
                }
                if sanitizer_meta.get("sanitized"):
                    self.append_event(
                        agent,
                        "running",
                        f"transcript sanitizer modified {sanitizer_meta['modifications_count']} fragments",
                    )
            if mem["injected"]:
                self.broadcast()
            elif agent_target_info.get("injected"):
                self.broadcast()
            elif sanitizer_meta.get("sanitized"):
                self.broadcast()

            if sanitizer_meta.get("sanitized"):
                self.emit_system_event(
                    "sanitizer_modified",
                    f"{label} transcript filtered {sanitizer_meta['modifications_count']} fragments",
                    severity="warn",
                    feature="transcript_sanitizer",
                )

            reply = ""
            meta: dict[str, Any] = {}
            try:
                if target == "claude":
                    with self.claude_exec_lock:
                        reply, meta = call_launcher(
                            self.launcher,
                            self.conf,
                            target,
                            injected_message,
                            session_id=session_id or None,
                            resume_session=resume_session,
                            skip_memory=skip_memory,
                            memory_result=mem,
                            target_info=agent_target_info,
                            cwd_override=cwd_override,
                            room_id=self.room_id,
                            sanitizer_meta=sanitizer_meta,
                            version_meta={
                                **gate,
                                "recheck_policy": recheck["policy"],
                                "recheck_allowed": recheck["allowed"],
                                "recheck_result": recheck["result"],
                                "recheck_reason": recheck["reason"],
                                "recheck_changed_fields": recheck["changed_fields"],
                                "startup_snapshot": self.version_snapshots[target],
                                "invocation_snapshot": invocation_snapshot,
                            },
                        )
                else:
                    reply, meta = call_launcher_stream(
                        self.launcher,
                        self.conf,
                        target,
                        injected_message,
                        session_id=session_id or None,
                        resume_session=resume_session,
                        skip_memory=skip_memory,
                        memory_result=mem,
                        target_info=agent_target_info,
                        sanitizer_meta=sanitizer_meta,
                        version_meta={
                            **gate,
                            "recheck_policy": recheck["policy"],
                            "recheck_allowed": recheck["allowed"],
                            "recheck_result": recheck["result"],
                            "recheck_reason": recheck["reason"],
                            "recheck_changed_fields": recheck["changed_fields"],
                            "startup_snapshot": self.version_snapshots[target],
                            "invocation_snapshot": invocation_snapshot,
                        },
                        on_stderr=lambda line: self._handle_codex_stderr(agent, line),
                        on_event=lambda event: self._handle_codex_runner_event(item, agent, event),
                        room_id=self.room_id,
                    )
            except Exception as exc:  # pragma: no cover - defensive
                meta = {"session_confirmed": False, "error": str(exc)}
                reply = f"[错误] {exc}"

            confirmed = bool(meta.get("session_confirmed"))
            with self.lock:
                agent["phase"] = "verifying"
                agent["phase_label"] = "整理验真结果"
                agent["next_step"] = "生成可复制的 verify-rid / resume"
                agent["current_detail"] = "launcher 已返回，正在整理审计结果"
                self.append_event(agent, "running", "launcher 已返回，正在整理审计结果")
            self.broadcast()

            with self.lock:
                agent["finished_at"] = now_iso()
                agent["reply"] = reply
                agent["meta"] = meta
                agent["confirmed"] = confirmed
                agent["status"] = "done"
                agent["pending_approval"] = None
                agent["phase"] = "done"
                agent["phase_label"] = "已完成并验真" if confirmed else "已完成，等待人工复核"
                agent["next_step"] = (
                    "可复制 verify-rid / resume 继续复核"
                    if confirmed
                    else "建议展开审计信息，按 verify-rid 做人工复核"
                )
                agent["current_detail"] = (
                    "session 验真已通过"
                    if confirmed
                    else "执行已完成，但系统自动验真未通过"
                )
                self.append_event(
                    agent,
                    "done",
                    "已生成验真结果" if confirmed else "执行完成，但验真未通过",
                )

                # 推进会议上下文游标，下次持久 session 只注入增量
                if target == "claude":
                    self.claude_meeting_cursor = next_cursor
                else:
                    self.codex_meeting_cursor = next_cursor
                    self._release_agent_locks(agent)

                if target == "claude":
                    resolved = meta.get("session_id") or session_id
                    if meta.get("exit_code") == 0 and resolved:
                        self._append_claude_session(resolved)
                        self.current_claude_session = resolved
                elif target == "codex" and meta.get("session_id"):
                    self.latest_codex_session = meta["session_id"]
            self._persist_room_state()
            self.broadcast()

    def _handle_codex_stderr(self, agent: dict[str, Any], line: str) -> None:
        event = self._parse_codex_stderr_event(line)
        if not event:
            return
        self._set_agent_phase(
            agent,
            event["phase"],
            event["phase_label"],
            event["next_step"],
            event["current_detail"],
            event.get("event_detail"),
        )

    def resolve_approval(
        self,
        item_id: str,
        target: str,
        request_id: str,
        decision: str,
        scope: str,
    ) -> bool:
        key = (item_id, target, request_id)
        with self.lock:
            waiter = self.pending_approvals.get(key)
            if waiter is None:
                return False
            waiter["response"] = {
                "type": "approval_response",
                "request_id": request_id,
                "decision": decision,
                "scope": scope,
            }
            agent = waiter["agent"]
            agent["pending_approval"] = None
            if decision in {"decline", "cancel"}:
                self._release_agent_locks(agent)
            self.append_event(agent, "running", f"审批已处理: {decision} ({scope})")
            waiter["event"].set()
        self._persist_room_state()
        self.broadcast()
        return True

    def _await_approval(self, item: dict[str, Any], agent: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
        request_id = str(event.get("request_id", ""))
        timeout_sec = float(event.get("timeout_sec", 120) or 120)
        request_payload = event.get("request", {}) or {}
        operation = classify_operation(request_payload)
        key = (item["id"], agent["target"], request_id)
        waiter = {"event": threading.Event(), "response": None, "agent": agent}
        if operation.get("requires_lock") and self.hardening.operation_locks == "enabled":
            owner = f"{self.room_id}:{agent['target']}:{request_id}"
            decision = self.operation_locks.acquire(
                owner,
                operation["class_name"],
                operation["resource_name"],
                self.hardening.lock_timeout_sec,
            )
            if not decision.granted:
                self.emit_system_event(
                    "lock_timeout",
                    f"{agent['label']} denied {operation['summary']} after {decision.wait_sec:.1f}s",
                    severity="warn",
                    feature="operation_locks",
                )
                with self.lock:
                    self.append_event(agent, "running", f"lock timeout: {operation['summary']}")
                self.broadcast()
                return {
                    "type": "approval_response",
                    "request_id": request_id,
                    "decision": "decline",
                    "scope": "turn",
                }
            if operation.get("class_name") == "ports" and self.hardening.shared_host_collision_guard == "enabled":
                try:
                    port_value = int(str(operation.get("resource_name", "")).split(":", 1)[1])
                except (IndexError, ValueError):
                    port_value = 0
                reservation = self.port_registry.reserve(
                    port_value,
                    owner,
                    {"room_id": self.room_id, "target": agent["target"], "request_id": request_id},
                )
                if not reservation.get("granted"):
                    self.operation_locks.release_owner(owner)
                    self.emit_system_event(
                        "port_reservation_conflict",
                        f"{agent['label']} denied port reservation {port_value}",
                        severity="warn",
                        feature="shared_host_collision_guard",
                    )
                    with self.lock:
                        self.append_event(agent, "running", f"port reservation conflict: {port_value}")
                    self.broadcast()
                    return {
                        "type": "approval_response",
                        "request_id": request_id,
                        "decision": "decline",
                        "scope": "turn",
                    }
            with self.lock:
                owners = list(agent.get("held_lock_owners") or [])
                owners.append(owner)
                agent["held_lock_owners"] = owners
                self.append_event(
                    agent,
                    "running",
                    f"lock acquired: {decision.resource_lock or decision.class_lock}",
                )
            self.emit_system_event(
                "lock_acquired",
                f"{agent['label']} acquired {decision.resource_lock or decision.class_lock}",
                severity="info",
                feature="operation_locks",
            )
        with self.lock:
            agent["pending_approval"] = {
                "request_id": request_id,
                "request_kind": event.get("request_kind", ""),
                "summary": event.get("summary", ""),
                "request": request_payload,
                "timeout_sec": timeout_sec,
                "thread_id": event.get("thread_id", ""),
                "turn_id": event.get("turn_id", ""),
                "operation": operation,
            }
            agent["phase"] = "approval_wait"
            agent["phase_label"] = "等待你的审批"
            agent["next_step"] = "点击批准 / 拒绝 / 取消后，Codex 才会继续"
            agent["current_detail"] = event.get("summary", "Codex 请求审批")
            self.append_event(agent, "running", f"审批请求: {event.get('summary', 'Codex 请求审批')}")
            self.pending_approvals[key] = waiter
        self._persist_room_state()
        self.broadcast()
        waiter["event"].wait(timeout=timeout_sec)
        with self.lock:
            self.pending_approvals.pop(key, None)
            response = waiter["response"] or {
                "type": "approval_response",
                "request_id": request_id,
                "decision": "decline",
                "scope": "turn",
            }
            agent["pending_approval"] = None
            if waiter["response"] is None:
                self.append_event(agent, "running", "审批超时，默认拒绝本次请求")
                self._release_agent_locks(agent)
        self._persist_room_state()
        self.broadcast()
        return response

    def _handle_codex_runner_event(
        self,
        item: dict[str, Any],
        agent: dict[str, Any],
        event: dict[str, Any],
    ) -> dict[str, Any] | None:
        event_type = event.get("type", "")
        if event_type == "phase":
            self._set_agent_phase(
                agent,
                event.get("phase", "running"),
                event.get("phase_label", "Codex 状态更新"),
                event.get("next_step", "等待更多状态"),
                event.get("current_detail", ""),
                event.get("event_detail"),
            )
            return None
        if event_type == "session_state":
            thread_id = event.get("thread_id", "")
            with self.lock:
                if thread_id:
                    self.latest_codex_session = thread_id
                    agent.setdefault("meta", {})["session_id"] = thread_id
                    self.append_event(agent, "running", f"room session: {thread_id}")
            self._persist_room_state()
            self.broadcast()
            return None
        if event_type == "reply_delta":
            with self.lock:
                agent["reply"] = event.get("reply", agent.get("reply", ""))
            self.broadcast()
            return None
        if event_type == "approval_request":
            return self._await_approval(item, agent, event)
        if event_type == "approval_resolved":
            with self.lock:
                self.append_event(
                    agent,
                    "running",
                    f"审批已回传: {event.get('decision', 'decline')} ({event.get('scope', 'turn')})",
                )
                if event.get("decision") in {"decline", "cancel"}:
                    self._release_agent_locks(agent)
            self.broadcast()
            return None
        if event_type == "runner_error":
            with self.lock:
                agent["current_detail"] = str(event.get("error", "Codex runner error"))
                self.append_event(agent, "running", f"runner error: {event.get('error', 'unknown')}")
            self._mark_recovery_required(f"runner error: {event.get('error', 'unknown')}")
            self._persist_room_state()
            self.broadcast()
            return None
        return None


class Handler(BaseHTTPRequestHandler):
    server: "TrialogueHTTPServer"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_html()
            return
        if self.path == "/api/bootstrap":
            self._send_json(self.server.state.snapshot())
            return
        if self.path == "/ws":
            self._handle_ws()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/api/send", "/api/approval", "/api/recovery/reset", "/api/anchor/verify"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, status=HTTPStatus.BAD_REQUEST)
            return

        if self.path == "/api/send":
            text = str(payload.get("text", "")).strip()
            if not text:
                self._send_json({"error": "text is required"}, status=HTTPStatus.BAD_REQUEST)
                return

            try:
                item = self.server.state.submit(text)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            self._send_json({"ok": True, "item_id": item["id"], "rid": item["rid"]})
            return

        if self.path == "/api/recovery/reset":
            ok, reason = self.server.state.reset_recovery()
            if not ok:
                self._send_json({"error": reason}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"ok": True})
            return

        if self.path == "/api/anchor/verify":
            result = self.server.state._run_remote_verifier(trigger="manual", asynchronous=False) or {}
            self._send_json({"ok": True, "result": result})
            return

        item_id = str(payload.get("item_id", "")).strip()
        target = str(payload.get("target", "")).strip()
        request_id = str(payload.get("request_id", "")).strip()
        decision = str(payload.get("decision", "")).strip().lower()
        scope = str(payload.get("scope", "turn")).strip().lower() or "turn"
        if not item_id or not target or not request_id or decision not in {"accept", "decline", "cancel"}:
            self._send_json({"error": "invalid approval payload"}, status=HTTPStatus.BAD_REQUEST)
            return
        if scope not in {"turn", "session"}:
            self._send_json({"error": "invalid approval scope"}, status=HTTPStatus.BAD_REQUEST)
            return
        ok = self.server.state.resolve_approval(item_id, target, request_id, decision, scope)
        if not ok:
            self._send_json({"error": "approval request not found"}, status=HTTPStatus.NOT_FOUND)
            return
        self._send_json({"ok": True})

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _send_html(self) -> None:
        html = self.server.index_html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _handle_ws(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return
        accept = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("utf-8")
            ).digest()
        ).decode("ascii")

        self.send_response(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()

        sock = self.connection
        self.server.state.register_client(sock)
        try:
            send_ws_text(
                sock,
                json.dumps(
                    {"type": "state", "state": self.server.state.snapshot()},
                    ensure_ascii=False,
                ),
            )
            while True:
                data = sock.recv(1024)
                if not data:
                    break
        except OSError:
            pass
        finally:
            self.server.state.unregister_client(sock)


class TrialogueHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler_class, state, index_html):
        super().__init__(server_address, handler_class)
        self.state = state
        self.index_html = index_html


def send_ws_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    if len(payload) < 126:
        header = struct.pack("!BB", 0x81, len(payload))
    elif len(payload) < 65536:
        header = struct.pack("!BBH", 0x81, 126, len(payload))
    else:
        header = struct.pack("!BBQ", 0x81, 127, len(payload))
    sock.sendall(header + payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Trialogue v2 Web UI")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--launcher", required=True)
    parser.add_argument("--conf", required=True)
    parser.add_argument("--audit-log", required=True)
    parser.add_argument("--workdir", default=os.getcwd())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    os.chdir(args.workdir)
    index_html = (script_dir / "index.html").read_text(encoding="utf-8")
    state = TrialogueState(args.topic, args.launcher, args.conf, args.audit_log)
    server = TrialogueHTTPServer((args.host, args.port), Handler, state, index_html)

    print(f"Trialogue Web UI listening on http://{args.host}:{args.port}")
    print(f"topic: {args.topic}")
    print(f"workdir: {args.workdir}")
    print(f"audit: {args.audit_log}")
    server.serve_forever()


if __name__ == "__main__":
    main()
