#!/usr/bin/env python3
"""
Trialogue v3 Codex app-server runner.

Runs entirely inside the Codex cabin and bridges:
  broker stdin/stdout/stderr <-> codex app-server stdio

Protocol between broker and runner:
  - stdout: final assistant reply only
  - stderr: plain logs and JSON events prefixed by TRIALOGUE_CODEX_EVENT
  - stdin: JSON lines for approval responses
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import queue
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _audit import build_verify_commands, parse_audit_message, peel_context_wrappers
from _memory import build_injected_message, load_memory


EVENT_PREFIX = "TRIALOGUE_CODEX_EVENT "
BROKER_TIMEOUT_SEC = 300.0
DEFAULT_APPROVAL_TIMEOUT_SEC = 120.0


def load_conf_map(conf_path: str) -> dict[str, str]:
    conf: dict[str, str] = {}
    with open(conf_path, "r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            conf[key.strip()] = value.strip()
    return conf


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def sanitize_room_id(raw: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "-" for ch in (raw or "room"))
    cleaned = cleaned.strip("-._") or "room"
    digest = hashlib.sha256((raw or "room").encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[:48]}-{digest}"


def emit_event(payload: dict[str, Any]) -> None:
    sys.stderr.write(EVENT_PREFIX + json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stderr.flush()


def parse_sandbox_policy(mode: str, workspace: str) -> dict[str, Any]:
    if mode == "danger-full-access":
        return {"type": "dangerFullAccess"}
    if mode == "read-only":
        return {"type": "readOnly"}
    return {
        "type": "workspaceWrite",
        "writableRoots": [workspace],
        "networkAccess": False,
    }


def ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def read_json_file(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def write_json_file(path: str, payload: dict[str, Any]) -> None:
    ensure_parent(path)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


@dataclass
class PendingApproval:
    request_id: Any
    method: str
    params: dict[str, Any]
    timeout_sec: float


class RPCError(RuntimeError):
    def __init__(self, method: str, payload: dict[str, Any]):
        super().__init__(f"{method} failed: {payload}")
        self.method = method
        self.payload = payload


class AppServerClient:
    def __init__(self, cmd: list[str], env: dict[str, str], cwd: str):
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=cwd,
            env=env,
        )
        self._send_lock = threading.Lock()
        self._next_id = 1
        self._pending: dict[Any, queue.Queue] = {}
        self.notifications: queue.Queue[dict[str, Any]] = queue.Queue()
        self.stderr_lines: list[str] = []
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        for raw_line in self.proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                self.notifications.put({"method": "transport/stdout", "params": {"line": line}})
                continue
            msg_id = payload.get("id")
            if msg_id is not None and ("result" in payload or "error" in payload):
                waiter = self._pending.get(msg_id)
                if waiter is not None:
                    waiter.put(payload)
                    continue
            self.notifications.put(payload)

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        for raw_line in self.proc.stderr:
            self.stderr_lines.append(raw_line.rstrip("\n"))
            sys.stderr.write(raw_line)
            sys.stderr.flush()

    def _send(self, payload: dict[str, Any]) -> None:
        raw = json.dumps({"jsonrpc": "2.0", **payload}, ensure_ascii=False)
        with self._send_lock:
            if self.proc.stdin is None:
                raise RuntimeError("app-server stdin is unavailable")
            self.proc.stdin.write(raw + "\n")
            self.proc.stdin.flush()

    def request(self, method: str, params: dict[str, Any], timeout: float = BROKER_TIMEOUT_SEC) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._pending[request_id] = waiter
        try:
            self._send({"id": request_id, "method": method, "params": params})
            try:
                payload = waiter.get(timeout=timeout)
            except queue.Empty as exc:
                raise TimeoutError(f"{method} timed out after {timeout}s") from exc
        finally:
            self._pending.pop(request_id, None)
        if "error" in payload:
            raise RPCError(method, payload["error"])
        return payload.get("result", {})

    def respond(self, request_id: Any, result: dict[str, Any]) -> None:
        self._send({"id": request_id, "result": result})

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"method": method}
        if params:
            payload["params"] = params
        self._send(payload)

    def get_notification(self, timeout: float = 0.2) -> dict[str, Any] | None:
        try:
            return self.notifications.get(timeout=timeout)
        except queue.Empty:
            return None

    def wait(self, timeout: float = 5.0) -> int | None:
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None


class BrokerInput:
    def __init__(self) -> None:
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()

    def _reader(self) -> None:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            self.queue.put(payload)

    def wait_for_approval(self, request_id: Any, timeout_sec: float) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout_sec
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                payload = self.queue.get(timeout=min(0.5, remaining))
            except queue.Empty:
                continue
            if payload.get("type") != "approval_response":
                continue
            if payload.get("request_id") != request_id:
                continue
            return payload


class RawEventLogger:
    def __init__(self, path: str):
        self.path = path
        ensure_parent(path)
        self._lock = threading.Lock()

    def append(self, direction: str, payload: dict[str, Any]) -> None:
        record = {
            "ts": now_iso(),
            "direction": direction,
            "payload": payload,
        }
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")


class Runner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.conf = load_conf_map(args.conf)
        self.script_dir = str(Path(__file__).resolve().parent)
        self.bin_path = self.conf.get("CODEX_BIN", "").strip()
        if not self.bin_path:
            raise RuntimeError("配置缺少 CODEX_BIN")
        self.app_server_bin = self.conf.get("CODEX_APP_SERVER_BIN", self.bin_path).strip() or self.bin_path
        self.app_server_command = self.conf.get("CODEX_APP_SERVER_COMMAND", "").strip()
        self.runner_home = self.conf.get("CODEX_RUNNER_HOME", os.environ.get("HOME", "")).strip()
        self.runner_workspace = self.conf.get("CODEX_RUNNER_WORKSPACE", self.conf.get("WORKSPACE", os.getcwd())).strip()
        self.runner_audit_log = self.conf.get("CODEX_RUNNER_AUDIT_LOG", self.conf.get("AUDIT_LOG", "")).strip()
        self.events_dir = self.conf.get("CODEX_APP_EVENTS_DIR", os.path.join(self.runner_workspace, "state", "codex-events")).strip()
        self.room_state_dir = self.conf.get("CODEX_ROOM_STATE_DIR", os.path.join(self.runner_workspace, "state", "codex-rooms")).strip()
        self.sandbox_mode = (args.sandbox_mode or self.conf.get("CODEX_SANDBOX_MODE", "workspace-write")).strip()
        self.approval_mode = (args.approval_mode or self.conf.get("CODEX_APPROVAL_MODE", "on-request")).strip()
        self.memory_source_dir = self.conf.get("CODEX_MEMORY_SOURCE_DIR", os.path.join(self.runner_home, ".codex-facts")).strip()
        self.memory_live_dir = self.conf.get("CODEX_MEMORY_LIVE_DIR", os.path.join(self.runner_workspace, "state", "codex-memory-live")).strip()
        self.sessions_root = self.conf.get("CODEX_SESSIONS", os.path.join(self.runner_home, ".codex", "sessions")).strip()
        self.runner_user = self.conf.get("CODEX_RUNNER_USER", "codex-agent").strip()
        self.model = self.conf.get("CODEX_MODEL", "").strip() or None
        self.model_provider = self.conf.get("CODEX_MODEL_PROVIDER", "").strip() or None
        self.service_tier = self.conf.get("CODEX_SERVICE_TIER", "").strip() or None
        self.room_id = sanitize_room_id(args.room_id or os.environ.get("TRIALOGUE_ROOM_ID", "default-room"))
        self.target_name = args.target_name or "meeting"
        self.target_source = args.target_source or "default"
        self.target_path = args.target_path or ""
        self.target_cwd_override = args.target_cwd_override or ""
        self.room_state_path = os.path.join(self.room_state_dir, f"{self.room_id}.json")
        self.room_state = read_json_file(self.room_state_path)
        self.thread_id = str(self.room_state.get("thread_id", "") or "")
        self.thread_path = str(self.room_state.get("thread_path", "") or "")
        self.turn_id = ""
        self.final_reply = ""
        self.final_reply_chunks: list[str] = []
        self.agent_item_id = ""
        self.command_output_tail = ""
        self.approval_events: list[dict[str, Any]] = []
        self.raw_event_log_path = ""
        self.meta: dict[str, Any] = {}
        self.app_client: AppServerClient | None = None
        self.broker_input = BrokerInput()
        self.message = args.message
        self.message_body = args.message
        self.rid = ""
        self.nonce = ""
        self.msg_sha256 = ""
        self.memory_meta: dict[str, Any] = {}
        self.meeting_info: dict[str, Any] = {}
        self.target_info: dict[str, Any] = {}
        self.confirmation_method = "unconfirmed"
        self.session_confirmed = False
        self.exit_code = 1
        self.started_at = now_iso()
        self.cwd = self._resolve_cwd()

    def _resolve_cwd(self) -> str:
        override = (self.target_cwd_override or "").strip()
        if override:
            return override
        target_path = (self.target_path or "").strip()
        if target_path:
            return target_path
        return self.runner_workspace

    def _prepare_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["HOME"] = self.runner_home
        env["XDG_CONFIG_HOME"] = env.get("XDG_CONFIG_HOME", os.path.join(self.runner_home, ".config"))
        env["XDG_CACHE_HOME"] = env.get("XDG_CACHE_HOME", os.path.join(self.runner_home, ".cache"))
        env["TRIALOGUE_CODEX_MEMORY_SOURCE_DIR"] = self.memory_source_dir
        env["TRIALOGUE_CODEX_MEMORY_LIVE_DIR"] = self.memory_live_dir
        return env

    def _prepare_message(self) -> None:
        os.environ["TRIALOGUE_CODEX_MEMORY_SOURCE_DIR"] = self.memory_source_dir
        os.environ["TRIALOGUE_CODEX_MEMORY_LIVE_DIR"] = self.memory_live_dir
        memory_result = load_memory("codex", target_name=self.target_name)
        self.memory_meta = {
            "injected": memory_result.get("injected", False),
            "profile": memory_result.get("profile", "none"),
            "files": memory_result.get("files", []),
            "source_files": memory_result.get("source_files", []),
            "bytes": memory_result.get("bytes", 0),
            "mirror_generated_at": memory_result.get("mirror_generated_at", ""),
            "sha256_claimed": memory_result.get("sha256", ""),
        }
        self.message = build_injected_message(memory_result, self.message)
        self.meeting_info, self.target_info, memory_info, message_without_context = peel_context_wrappers(self.message)
        self.memory_meta["sha256_verified"] = memory_info.get("sha256_verified", "")
        self.memory_meta["sha256_match"] = memory_info.get("sha256_match", False)
        parsed = parse_audit_message(message_without_context)
        self.message_body = parsed["message_body"]
        self.rid = parsed["rid"]
        self.nonce = parsed["nonce"]
        self.msg_sha256 = parsed["msg_sha256"]

    def _emit_phase(
        self,
        phase: str,
        phase_label: str,
        next_step: str,
        current_detail: str,
        event_detail: str | None = None,
    ) -> None:
        payload = {
            "type": "phase",
            "phase": phase,
            "phase_label": phase_label,
            "next_step": next_step,
            "current_detail": current_detail,
        }
        if event_detail:
            payload["event_detail"] = event_detail
        emit_event(payload)

    def _persist_room_state(self, *, broken: bool | None = None) -> None:
        payload = dict(self.room_state)
        payload.update(
            {
                "room_id": self.room_id,
                "thread_id": self.thread_id,
                "thread_path": self.thread_path,
                "broken": payload.get("broken", False) if broken is None else bool(broken),
                "updated_at": now_iso(),
                "last_rid": self.rid,
                "last_turn_id": self.turn_id,
                "last_raw_event_log": self.raw_event_log_path,
            }
        )
        self.room_state = payload
        write_json_file(self.room_state_path, payload)

    def _map_approval_response(self, pending: PendingApproval, broker_payload: dict[str, Any] | None) -> dict[str, Any]:
        decision = (broker_payload or {}).get("decision", "decline")
        scope = (broker_payload or {}).get("scope", "turn")
        if pending.method == "item/commandExecution/requestApproval":
            if decision == "accept":
                return {"decision": "acceptForSession" if scope == "session" else "accept"}
            if decision == "cancel":
                return {"decision": "cancel"}
            return {"decision": "decline"}
        if pending.method == "item/fileChange/requestApproval":
            if decision == "accept":
                return {"decision": "acceptForSession" if scope == "session" else "accept"}
            if decision == "cancel":
                return {"decision": "cancel"}
            return {"decision": "decline"}
        requested_permissions = pending.params.get("permissions") or {}
        if decision == "accept":
            return {"permissions": requested_permissions, "scope": "session" if scope == "session" else "turn"}
        return {"permissions": {}, "scope": "turn"}

    def _approval_summary(self, pending: PendingApproval) -> str:
        params = pending.params
        if pending.method == "item/commandExecution/requestApproval":
            command = (params.get("command") or "").strip()
            cwd = params.get("cwd") or self.cwd
            return f"命令执行审批: {command or '(empty command)'} @ {cwd}"
        if pending.method == "item/fileChange/requestApproval":
            changes = params.get("changes") or []
            return f"文件变更审批: {len(changes)} 项"
        if pending.method == "item/permissions/requestApproval":
            return f"权限审批: {json.dumps(params.get('permissions') or {}, ensure_ascii=False)}"
        return pending.method

    def _handle_server_request(self, payload: dict[str, Any], logger: RawEventLogger) -> None:
        request_id = payload.get("id")
        method = payload.get("method", "")
        params = payload.get("params") or {}
        if method not in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            if self.app_client is not None:
                self.app_client.respond(request_id, {})
            return

        timeout_sec = float(self.conf.get("CODEX_APPROVAL_TIMEOUT_SEC", DEFAULT_APPROVAL_TIMEOUT_SEC))
        pending = PendingApproval(request_id=request_id, method=method, params=params, timeout_sec=timeout_sec)
        approval_event = {
            "type": "approval_request",
            "request_id": request_id,
            "request_kind": method.rsplit("/", 1)[0].split("/")[-1],
            "method": method,
            "summary": self._approval_summary(pending),
            "request": params,
            "thread_id": params.get("threadId", self.thread_id),
            "turn_id": params.get("turnId", self.turn_id),
            "timeout_sec": timeout_sec,
        }
        self.approval_events.append(
            {
                "request_id": request_id,
                "method": method,
                "params": params,
                "requested_at": now_iso(),
            }
        )
        emit_event(approval_event)
        broker_payload = self.broker_input.wait_for_approval(request_id, timeout_sec)
        resolved = self._map_approval_response(pending, broker_payload)
        logger.append("broker_response", {"request_id": request_id, "payload": broker_payload or {"decision": "timeout"}})
        if self.app_client is not None:
            self.app_client.respond(request_id, resolved)
        emit_event(
            {
                "type": "approval_resolved",
                "request_id": request_id,
                "method": method,
                "decision": (broker_payload or {}).get("decision", "decline"),
                "scope": (broker_payload or {}).get("scope", "turn"),
            }
        )

    def _handle_notification(self, payload: dict[str, Any], logger: RawEventLogger) -> bool:
        method = payload.get("method", "")
        params = payload.get("params") or {}
        if method == "thread/started":
            thread = params.get("thread") or {}
            self.thread_id = thread.get("id", self.thread_id)
            self.thread_path = thread.get("path") or self.thread_path
            self._persist_room_state(broken=False)
            emit_event(
                {
                    "type": "session_state",
                    "thread_id": self.thread_id,
                    "thread_path": self.thread_path,
                    "room_state_path": self.room_state_path,
                }
            )
            return False
        if method == "turn/started":
            turn = params.get("turn") or {}
            self.turn_id = turn.get("id", self.turn_id)
            self._emit_phase(
                "turn_started",
                "Codex 已开始当前轮次",
                "等待 agent message / tool call / approval 事件",
                f"thread={params.get('threadId', self.thread_id)} turn={self.turn_id}",
                "turn/start 已被 app-server 接收",
            )
            return False
        if method == "item/agentMessage/delta":
            delta = params.get("delta", "")
            self.final_reply_chunks.append(delta)
            self.final_reply = "".join(self.final_reply_chunks)
            emit_event(
                {
                    "type": "reply_delta",
                    "delta": delta,
                    "reply": self.final_reply,
                }
            )
            return False
        if method == "item/commandExecution/outputDelta":
            delta = params.get("delta", "")
            if delta:
                self.command_output_tail = (self.command_output_tail + delta)[-1200:]
                self._emit_phase(
                    "tool_running",
                    "Codex 正在执行命令",
                    "等待命令返回或新的审批事件",
                    self.command_output_tail.strip() or delta.strip(),
                    "命令输出已更新",
                )
            return False
        if method == "item/completed":
            item = params.get("item") or {}
            item_type = item.get("type")
            if item_type == "agentMessage":
                text = item.get("text", "")
                if text:
                    self.final_reply = text
            elif item_type == "commandExecution":
                command = item.get("command", "")
                status = item.get("status", "")
                exit_code = item.get("exitCode")
                detail = f"{command} -> {status}"
                if exit_code is not None:
                    detail += f" (exit {exit_code})"
                self._emit_phase(
                    "tool_completed",
                    "Codex 命令已返回",
                    "继续等待 agent 汇总或下一步工具事件",
                    detail,
                    detail,
                )
            elif item_type == "fileChange":
                changes = item.get("changes") or []
                self._emit_phase(
                    "file_change",
                    "Codex 已完成文件修改",
                    "等待 agent 汇总最终答复",
                    f"本轮文件变更数: {len(changes)}",
                    f"文件变更数: {len(changes)}",
                )
            return False
        if method == "turn/completed":
            turn = params.get("turn") or {}
            status = turn.get("status", "")
            if status == "completed":
                self.exit_code = 0
            self._emit_phase(
                "finalizing",
                "Codex 正在整理最终结果",
                "写入审计、room state 和 meta",
                f"turn status: {status or 'unknown'}",
                f"turn/completed: {status or 'unknown'}",
            )
            return True
        if method == "thread/status/changed":
            status = (params.get("thread") or {}).get("status") or ""
            emit_event({"type": "thread_status", "status": status, "thread_id": self.thread_id})
            return False
        if method == "error":
            emit_event({"type": "runner_error", "error": params})
            return False
        return False

    def _start_or_resume_thread(self) -> None:
        assert self.app_client is not None
        thread_params = {
            "cwd": self.cwd,
            "approvalPolicy": self.approval_mode,
            "sandbox": self.sandbox_mode,
            "model": self.model,
            "modelProvider": self.model_provider,
            "serviceTier": self.service_tier,
            "personality": "pragmatic",
            "serviceName": "trialogue-codex-runner",
            "ephemeral": False,
        }
        if self.thread_id and not self.room_state.get("broken"):
            try:
                result = self.app_client.request("thread/resume", {"threadId": self.thread_id, **thread_params})
                thread = result.get("thread") or {}
                self.thread_id = thread.get("id", self.thread_id)
                self.thread_path = thread.get("path") or self.thread_path
                self._persist_room_state(broken=False)
                emit_event(
                    {
                        "type": "session_state",
                        "thread_id": self.thread_id,
                        "thread_path": self.thread_path,
                        "room_state_path": self.room_state_path,
                        "resumed": True,
                    }
                )
                return
            except Exception as exc:
                self._persist_room_state(broken=True)
                self._emit_phase(
                    "session_recovery",
                    "旧 Codex session 不可恢复",
                    "创建新的 room 级 thread",
                    str(exc),
                    "thread/resume 失败，切换到 thread/start",
                )

        result = self.app_client.request("thread/start", thread_params)
        thread = result.get("thread") or {}
        self.thread_id = thread.get("id", self.thread_id)
        self.thread_path = thread.get("path") or self.thread_path
        self._persist_room_state(broken=False)
        emit_event(
            {
                "type": "session_state",
                "thread_id": self.thread_id,
                "thread_path": self.thread_path,
                "room_state_path": self.room_state_path,
                "resumed": False,
            }
        )

    def _run_turn(self) -> None:
        assert self.app_client is not None
        result = self.app_client.request(
            "turn/start",
            {
                "threadId": self.thread_id,
                "input": [{"type": "text", "text": self.message, "text_elements": []}],
                "approvalPolicy": self.approval_mode,
                "cwd": self.cwd,
                "sandboxPolicy": parse_sandbox_policy(self.sandbox_mode, self.cwd),
                "personality": "pragmatic",
            },
        )
        turn = result.get("turn") or {}
        self.turn_id = turn.get("id", self.turn_id)

    def _write_summary_audit(self) -> None:
        meeting_info, target_info, _, _ = peel_context_wrappers(self.message)
        verify_commands = build_verify_commands(
            target="codex",
            rid=self.rid,
            nonce=self.nonce,
            session_id=self.thread_id,
            session_file=self.raw_event_log_path or self.thread_path or self.room_state_path,
            store_root=self.events_dir,
        )
        resume_prefix = (
            f"sudo -u {self.runner_user} env " if self.runner_user else "env "
        )
        resume_cmd = (
            f"{resume_prefix}"
            f"HOME={shlex.quote(self.runner_home)} "
            f"XDG_CONFIG_HOME={shlex.quote(os.path.join(self.runner_home, '.config'))} "
            f"XDG_CACHE_HOME={shlex.quote(os.path.join(self.runner_home, '.cache'))} "
            f"{shlex.quote(self.bin_path)} resume {shlex.quote(self.thread_id)}"
            if self.thread_id
            else ""
        )
        if resume_cmd:
            verify_commands["resume_command"] = resume_cmd
        if self.nonce and self.raw_event_log_path:
            verify_commands["verify_file_command"] = (
                f"rg -n --fixed-strings {shlex.quote(self.nonce)} {shlex.quote(self.raw_event_log_path)}"
            )
            verify_commands["verify_store_command"] = (
                f"rg -n --fixed-strings {shlex.quote(self.nonce)} {shlex.quote(self.events_dir)}"
            )

        self.session_confirmed = bool(self.thread_id and self.turn_id and not self.room_state.get("broken"))
        self.confirmation_method = "app_server_thread" if self.session_confirmed else "unconfirmed"
        confirmation = {
            "mode": "codex_app_server",
            "thread_id": self.thread_id,
            "thread_path": self.thread_path,
            "turn_id": self.turn_id,
            "room_id": self.room_id,
            "room_state_path": self.room_state_path,
            "approval_request_count": len(self.approval_events),
            "raw_event_log_path": self.raw_event_log_path,
        }
        record = {
            "timestamp": self.started_at,
            "target": "codex",
            "mode": "codex_app_server",
            "rid": self.rid,
            "nonce": self.nonce,
            "msg_sha256": self.msg_sha256,
            "message": self.message,
            "message_body": self.message_body,
            "audit_header_found": bool(self.rid),
            "audit_header_valid": True if self.rid else None,
            "binary_path": str(Path(self.bin_path).resolve()),
            "binary_sha256": hashlib.sha256(Path(self.bin_path).read_bytes()).hexdigest(),
            "cli_version": subprocess.run(
                [self.bin_path, "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._prepare_env(),
                cwd=self.cwd,
            ).stdout.strip() or "unknown",
            "pid": self.app_client.proc.pid if self.app_client else 0,
            "cli_ppid": os.getpid(),
            "cwd": self.cwd,
            "argv": shlex.split(self.app_server_command) if self.app_server_command else [self.app_server_bin, "app-server", "--listen", "stdio://"],
            "exit_code": self.exit_code,
            "session_id": self.thread_id,
            "session_source": "codex_app_server",
            "session_confirmed": self.session_confirmed,
            "session_file": self.thread_path or self.room_state_path,
            "confirmation_method": self.confirmation_method,
            "confirmation": confirmation,
            "verify_commands": verify_commands,
            "stdout": self.final_reply,
            "stderr": "\n".join(self.app_client.stderr_lines if self.app_client else []),
            "memory_injected": self.memory_meta.get("injected", False),
            "memory_profile": self.memory_meta.get("profile", "none"),
            "memory_files": self.memory_meta.get("files", []),
            "memory_source_files": self.memory_meta.get("source_files", []),
            "memory_sha256_claimed": self.memory_meta.get("sha256_claimed", ""),
            "memory_sha256_verified": self.memory_meta.get("sha256_verified", ""),
            "memory_sha256_match": self.memory_meta.get("sha256_match", False),
            "memory_bytes": self.memory_meta.get("bytes", 0),
            "memory_mirror_generated_at": self.memory_meta.get("mirror_generated_at", ""),
            "meeting_context_injected": meeting_info.get("injected", False),
            "meeting_context_sha256_claimed": meeting_info.get("sha256_claimed", ""),
            "meeting_context_sha256_verified": meeting_info.get("sha256_verified", ""),
            "meeting_context_sha256_match": meeting_info.get("sha256_match", False),
            "meeting_context_bytes": meeting_info.get("bytes", 0),
            "meeting_context_entries": meeting_info.get("entries", 0),
            "meeting_context_untrusted": meeting_info.get("untrusted", False),
            "meeting_context_semantic": meeting_info.get("semantic", ""),
            "target_context_injected": target_info.get("injected", False),
            "target_name": self.target_name,
            "target_source": self.target_source,
            "target_path": self.target_path,
            "target_cwd_override": self.target_cwd_override,
            "target_context_claimed_name": target_info.get("name", ""),
            "target_context_claimed_source": target_info.get("source", ""),
            "target_context_claimed_path": target_info.get("path", ""),
            "target_context_sha256_claimed": target_info.get("sha256_claimed", ""),
            "target_context_sha256_verified": target_info.get("sha256_verified", ""),
            "target_context_sha256_match": target_info.get("sha256_match", False),
            "target_context_env_match": True,
            "raw_event_log_path": self.raw_event_log_path,
            "room_state_path": self.room_state_path,
        }
        ensure_parent(self.runner_audit_log)
        with open(self.runner_audit_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        meta = {
            "rid": self.rid,
            "nonce": self.nonce,
            "msg_sha256": self.msg_sha256,
            "session_id": self.thread_id,
            "session_confirmed": self.session_confirmed,
            "session_file": self.thread_path or self.room_state_path,
            "confirmation_method": self.confirmation_method,
            "exit_code": self.exit_code,
            "resume_command": verify_commands.get("resume_command", ""),
            "verify_rid_command": verify_commands.get("verify_rid_command", ""),
            "verify_file_command": verify_commands.get("verify_file_command", ""),
            "verify_store_command": verify_commands.get("verify_store_command", ""),
            "memory_injected": self.memory_meta.get("injected", False),
            "memory_profile": self.memory_meta.get("profile", "none"),
            "memory_files": self.memory_meta.get("files", []),
            "memory_source_files": self.memory_meta.get("source_files", []),
            "memory_bytes": self.memory_meta.get("bytes", 0),
            "meeting_context_injected": meeting_info.get("injected", False),
            "meeting_context_untrusted": meeting_info.get("untrusted", False),
            "meeting_context_semantic": meeting_info.get("semantic", ""),
            "target_context_injected": target_info.get("injected", False),
            "target_name": self.target_name,
            "target_source": self.target_source,
            "target_path": self.target_path,
            "room_state_path": self.room_state_path,
            "raw_event_log_path": self.raw_event_log_path,
            "mode": "codex_app_server",
        }
        ensure_parent(self.args.meta_file)
        with open(self.args.meta_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        self.meta = meta

    def run(self) -> int:
        Path(self.events_dir).mkdir(parents=True, exist_ok=True)
        Path(self.room_state_dir).mkdir(parents=True, exist_ok=True)
        Path(self.runner_workspace).mkdir(parents=True, exist_ok=True)
        Path(self.memory_live_dir).mkdir(parents=True, exist_ok=True)

        self._prepare_message()
        event_name = f"{self.rid or 'no-rid'}-{int(time.time())}.jsonl"
        self.raw_event_log_path = os.path.join(self.events_dir, event_name)
        logger = RawEventLogger(self.raw_event_log_path)

        self._emit_phase(
            "runner_boot",
            "Codex app-server runner 已启动",
            "初始化 app-server 连接",
            f"room={self.room_id} cwd={self.cwd}",
            "runner 已接管当前请求",
        )

        cmd = shlex.split(self.app_server_command) if self.app_server_command else [self.app_server_bin, "app-server", "--listen", "stdio://"]
        env = self._prepare_env()
        self.app_client = AppServerClient(cmd=cmd, env=env, cwd=self.cwd)

        try:
            init_result = self.app_client.request(
                "initialize",
                {
                    "clientInfo": {"name": "trialogue-codex-runner", "version": "v3"},
                    "capabilities": {"experimentalApi": True},
                },
            )
            logger.append("server", {"result": init_result, "method": "initialize"})
            self.app_client.notify("initialized")
            self._emit_phase(
                "session_prepare",
                "正在准备 Codex room session",
                "尝试恢复旧 thread；若失败则创建新 thread",
                "initialize 已完成",
                "app-server initialize 完成",
            )
            self._start_or_resume_thread()
            self._run_turn()

            done = False
            while not done:
                message = self.app_client.get_notification(timeout=0.2)
                if message is None:
                    poll = self.app_client.wait(timeout=0.0)
                    if poll is not None and poll != 0:
                        raise RuntimeError(f"codex app-server exited early with code {poll}")
                    continue
                logger.append("server", message)
                if message.get("method"):
                    if "id" in message:
                        self._handle_server_request(message, logger)
                    else:
                        done = self._handle_notification(message, logger)

            self.exit_code = 0 if self.exit_code == 0 else 1
            self._persist_room_state(broken=False)
            self._write_summary_audit()
            sys.stdout.write(self.final_reply)
            sys.stdout.flush()
            return 0
        except Exception as exc:
            self.exit_code = 1
            self._persist_room_state(broken=True)
            emit_event({"type": "runner_error", "error": str(exc), "room_state_path": self.room_state_path})
            ensure_parent(self.args.meta_file)
            with open(self.args.meta_file, "w", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "rid": self.rid,
                            "nonce": self.nonce,
                            "msg_sha256": self.msg_sha256,
                            "session_id": self.thread_id,
                            "session_confirmed": False,
                            "session_file": self.thread_path or self.room_state_path,
                            "confirmation_method": "runner_error",
                            "exit_code": 1,
                            "error": str(exc),
                            "mode": "codex_app_server",
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            raise
        finally:
            if self.app_client is not None and self.app_client.proc.poll() is None:
                self.app_client.proc.terminate()
                self.app_client.wait(timeout=2.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trialogue Codex app-server runner")
    parser.add_argument("--message", required=True)
    parser.add_argument("--conf", required=True)
    parser.add_argument("--meta-file", required=True)
    parser.add_argument("--sandbox-mode", default="")
    parser.add_argument("--approval-mode", default="")
    parser.add_argument("--room-id", default="")
    parser.add_argument("--target-name", default="")
    parser.add_argument("--target-source", default="")
    parser.add_argument("--target-path", default="")
    parser.add_argument("--target-cwd-override", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    runner = Runner(args)
    return runner.run()


if __name__ == "__main__":
    sys.exit(main())
