#!/usr/bin/env python3
"""
Trialogue v2 — 审计 + session 确认 + 元数据生成
由 launcher.sh 调用，所有输入通过环境变量和文件传递，零 shell 插值。

exit 0 = 审计日志 + 元数据均已写入
exit 1 = 写入失败
"""

import hashlib
import json
import os
import re
import shlex
import sys
import time

AUDIT_HEADER_RE = re.compile(
    r"^\[TRIALOGUE-AUDIT rid=(?P<rid>\S+) nonce=(?P<nonce>\S+) sha256=(?P<sha>[0-9a-f]{64})\]$"
)
SESSION_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4,}-[0-9a-f]{4}-[0-9a-f]{12}"
)
MEMORY_HEADER_RE = re.compile(
    r"^\[MEMORY-CONTEXT readonly=true profile=(?P<profile>\S+)"
    r" sha256=(?P<sha>[0-9a-f]{64})"
    r"(?:\s+files=(?P<files>\S+))?\]$"
)
MEETING_HEADER_RE = re.compile(
    r"^\[MEETING-CONTEXT readonly=true"
    r"(?:\s+untrusted=(?P<untrusted>\S+))?"
    r"(?:\s+semantic=(?P<semantic>\S+))?"
    r" sha256=(?P<sha>[0-9a-f]{64})"
    r" entries=(?P<entries>\d+)"
    r"(?:\s+mode=(?P<mode>\S+))?\]$"
)
TARGET_HEADER_RE = re.compile(
    r"^\[TARGET-CONTEXT readonly=true target=(?P<target>\S+)"
    r" source=(?P<source>\S+)"
    r" sha256=(?P<sha>[0-9a-f]{64})"
    r" path=(?P<path>\S+)\]$"
)
CLAUDE_CONFIRM_ATTEMPTS = 5
CLAUDE_CONFIRM_SLEEP_SEC = 0.2


def env(key, default=""):
    return os.environ.get(key, default)


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (FileNotFoundError, PermissionError):
        return ""


def parse_memory_context(message):
    """从消息中提取并剥离 [MEMORY-CONTEXT] 块。

    返回 (memory_info, remaining_message)
    memory_info = {"injected": bool, "profile": str, "sha256": str, "bytes": int}
    """
    no_memory = {"injected": False, "profile": "none", "sha256_claimed": "", "sha256_verified": "", "sha256_match": False, "bytes": 0, "files": []}

    if not message.startswith("[MEMORY-CONTEXT "):
        return no_memory, message

    end_tag = "[/MEMORY-CONTEXT]"
    end_pos = message.find(end_tag)
    if end_pos == -1:
        return no_memory, message

    block = message[:end_pos + len(end_tag)]
    remaining = message[end_pos + len(end_tag):].lstrip("\n")

    # 解析头部
    first_line = block.split("\n", 1)[0]
    match = MEMORY_HEADER_RE.fullmatch(first_line.strip())
    if not match:
        return no_memory, message

    # 提取正文并独立重算 hash（不信任头部自报的 sha256）
    body_start = block.find("\n") + 1
    body_end = block.rfind("\n" + end_tag)
    body = block[body_start:body_end] if body_end > body_start else ""
    body_bytes = body.encode("utf-8")
    actual_sha256 = hashlib.sha256(body_bytes).hexdigest()
    claimed_sha256 = match.group("sha")

    files_raw = match.group("files") or ""
    files_list = [f for f in files_raw.split(",") if f] if files_raw else []

    return {
        "injected": True,
        "profile": match.group("profile"),
        "sha256_claimed": claimed_sha256,
        "sha256_verified": actual_sha256,
        "sha256_match": actual_sha256 == claimed_sha256,
        "bytes": len(body_bytes),
        "files": files_list,
    }, remaining


def parse_meeting_context(message):
    no_meeting = {
        "injected": False,
        "sha256_claimed": "",
        "sha256_verified": "",
        "sha256_match": False,
        "bytes": 0,
        "entries": 0,
        "untrusted": False,
        "semantic": "",
    }

    if not message.startswith("[MEETING-CONTEXT "):
        return no_meeting, message

    end_tag = "[/MEETING-CONTEXT]"
    end_pos = message.find(end_tag)
    if end_pos == -1:
        return no_meeting, message

    block = message[:end_pos + len(end_tag)]
    remaining = message[end_pos + len(end_tag):].lstrip("\n")

    first_line = block.split("\n", 1)[0]
    match = MEETING_HEADER_RE.fullmatch(first_line.strip())
    if not match:
        return no_meeting, message

    body_start = block.find("\n") + 1
    body_end = block.rfind("\n" + end_tag)
    body = block[body_start:body_end] if body_end > body_start else ""
    body_bytes = body.encode("utf-8")
    actual_sha256 = hashlib.sha256(body_bytes).hexdigest()
    claimed_sha256 = match.group("sha")

    return {
        "injected": True,
        "sha256_claimed": claimed_sha256,
        "sha256_verified": actual_sha256,
        "sha256_match": actual_sha256 == claimed_sha256,
        "bytes": len(body_bytes),
        "entries": int(match.group("entries")),
        "untrusted": (match.group("untrusted") or "").lower() == "true",
        "semantic": match.group("semantic") or "",
        "mode": match.group("mode") or "full",
    }, remaining


def parse_target_context(message):
    no_target = {
        "injected": False,
        "name": "meeting",
        "source": "default",
        "path": "",
        "sha256_claimed": "",
        "sha256_verified": "",
        "sha256_match": False,
    }

    if not message.startswith("[TARGET-CONTEXT "):
        return no_target, message

    end_tag = "[/TARGET-CONTEXT]"
    end_pos = message.find(end_tag)
    if end_pos == -1:
        return no_target, message

    block = message[:end_pos + len(end_tag)]
    remaining = message[end_pos + len(end_tag):].lstrip("\n")

    first_line = block.split("\n", 1)[0]
    match = TARGET_HEADER_RE.fullmatch(first_line.strip())
    if not match:
        return no_target, message

    body_start = block.find("\n") + 1
    body_end = block.rfind("\n" + end_tag)
    body = block[body_start:body_end] if body_end > body_start else ""
    actual_sha256 = hashlib.sha256(body.encode("utf-8")).hexdigest()

    return {
        "injected": True,
        "name": match.group("target"),
        "source": match.group("source"),
        "path": match.group("path"),
        "sha256_claimed": match.group("sha"),
        "sha256_verified": actual_sha256,
        "sha256_match": actual_sha256 == match.group("sha"),
    }, remaining


def parse_audit_message(message):
    first_line, sep, body = message.partition("\n")
    match = AUDIT_HEADER_RE.fullmatch(first_line.strip())
    if not match:
        return {
            "rid": "",
            "nonce": "",
            "msg_sha256": "",
            "message_body": message,
            "header_found": False,
            "header_valid": False,
        }

    # `body` here is the original user message as passed by chat.py:
    # wrapped_message = header + "\n" + original_message
    original_message = body if sep else message
    body_sha256 = hashlib.sha256(original_message.encode("utf-8")).hexdigest()
    return {
        "rid": match.group("rid"),
        "nonce": match.group("nonce"),
        "msg_sha256": match.group("sha"),
        "message_body": original_message,
        "header_found": True,
        "header_valid": body_sha256 == match.group("sha"),
    }


def peel_context_wrappers(message):
    meeting_info = {
        "injected": False,
        "sha256_claimed": "",
        "sha256_verified": "",
        "sha256_match": False,
        "bytes": 0,
        "entries": 0,
        "untrusted": False,
        "semantic": "",
    }
    target_info = {
        "injected": False,
        "name": "meeting",
        "source": "default",
        "path": "",
        "sha256_claimed": "",
        "sha256_verified": "",
        "sha256_match": False,
    }
    memory_info = {
        "injected": False,
        "profile": "none",
        "sha256_claimed": "",
        "sha256_verified": "",
        "sha256_match": False,
        "bytes": 0,
        "files": [],
    }

    remaining = message
    changed = True
    while changed:
        changed = False
        if not meeting_info["injected"] and remaining.startswith("[MEETING-CONTEXT "):
            parsed, stripped = parse_meeting_context(remaining)
            if parsed["injected"]:
                meeting_info = parsed
                remaining = stripped
                changed = True
                continue
        if not target_info["injected"] and remaining.startswith("[TARGET-CONTEXT "):
            parsed, stripped = parse_target_context(remaining)
            if parsed["injected"]:
                target_info = parsed
                remaining = stripped
                changed = True
                continue
        if not memory_info["injected"] and remaining.startswith("[MEMORY-CONTEXT "):
            parsed, stripped = parse_memory_context(remaining)
            if parsed["injected"]:
                memory_info = parsed
                remaining = stripped
                changed = True
                continue

    return meeting_info, target_info, memory_info, remaining


def file_contains(path, needle):
    if not needle:
        return False
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if needle in line:
                    return True
    except (FileNotFoundError, PermissionError, IsADirectoryError):
        return False
    return False


def find_codex_nonce_matches(root_dir, nonce):
    matches = []
    if not nonce or not os.path.isdir(root_dir):
        return matches

    for root, _, files in os.walk(root_dir):
        for name in files:
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(root, name)
            if file_contains(path, nonce):
                matches.append(path)

    return sorted(matches)


def extract_session_id(path):
    match = SESSION_ID_RE.search(os.path.basename(path))
    return match.group(0) if match else ""


def read_last_claude_user_message(path):
    last_user_msg = ""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "user":
                    continue
                content = obj.get("message", {}).get("content", "")
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        if isinstance(item, dict):
                            parts.append(item.get("text", ""))
                    content = " ".join(parts)
                if content:
                    last_user_msg = content
    except (FileNotFoundError, PermissionError):
        pass
    return last_user_msg


def build_verify_commands(target, rid, nonce, session_id, session_file, store_root):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    commands = {
        "verify_rid_command": "",
        "resume_command": "",
        "verify_file_command": "",
        "verify_store_command": "",
    }

    if rid:
        commands["verify_rid_command"] = (
            f"{os.path.join(script_dir, 'verify-rid.sh')} {shlex.quote(rid)}"
        )

    if target == "claude" and session_id:
        commands["resume_command"] = f"claude --resume {session_id}"
    elif target == "codex" and session_id:
        commands["resume_command"] = f"codex resume {session_id}"

    if nonce and session_file:
        commands["verify_file_command"] = (
            f"rg -n --fixed-strings {shlex.quote(nonce)} {shlex.quote(session_file)}"
        )

    if nonce and store_root:
        commands["verify_store_command"] = (
            f"rg -n --fixed-strings {shlex.quote(nonce)} {shlex.quote(store_root)}"
        )

    return commands


def main():
    target = env("_L_TARGET")
    session_id = env("_L_SESSION_ID")
    resume_session = env("_L_RESUME_SESSION") == "1"
    cli_pid = int(env("_L_CLI_PID", "0"))
    exit_code = int(env("_L_EXIT_CODE", "1"))
    message = read_file(env("_L_MESSAGE_FILE"))
    stdout = read_file(env("_L_STDOUT_FILE"))
    stderr = read_file(env("_L_STDERR_FILE"))
    workdir = env("_L_WORKDIR") or os.getcwd()
    target_name_env = env("_L_TARGET_NAME", "meeting")
    target_source_env = env("_L_TARGET_SOURCE", "default")
    target_path_env = env("_L_TARGET_PATH")
    target_cwd_override = env("_L_TARGET_CWD_OVERRIDE")
    claude_resume_fallback = env("_L_CLAUDE_RESUME_FALLBACK") == "1"
    claude_resume_fallback_reason = env("_L_CLAUDE_RESUME_FALLBACK_REASON")
    claude_resume_original_session_id = env("_L_CLAUDE_RESUME_ORIGINAL_SESSION_ID")
    claude_resume_original_exit_code = env("_L_CLAUDE_RESUME_ORIGINAL_EXIT_CODE")

    meeting_info, target_info, memory_info, message_without_memory = peel_context_wrappers(message)
    target_env_match = (
        not target_info["injected"]
        or (
            target_info["name"] == target_name_env
            and target_info["source"] == target_source_env
            and target_info["path"] == target_path_env
        )
    )

    parsed = parse_audit_message(message_without_memory)
    rid = parsed["rid"]
    nonce = parsed["nonce"]
    msg_sha256 = parsed["msg_sha256"]
    message_body = parsed["message_body"]
    header_found = parsed["header_found"]
    header_valid = parsed["header_valid"]

    # ── 构建 argv ──
    bin_path = env("_L_BIN")
    if target == "claude":
        argv = [bin_path, "-p"]
        if resume_session:
            argv.extend(["--resume", session_id])
        else:
            argv.extend(["--session-id", session_id])
        argv.extend(["--output-format", "text", message])
    else:
        argv = [bin_path, "exec", message]

    session_confirmed = False
    confirmation = {}
    session_file = ""
    store_root = ""
    new_files = []
    confirmation_method = "unconfirmed"

    if target == "claude":
        claude_sessions = env("_L_CLAUDE_SESSIONS")
        claude_projects = env("_L_CLAUDE_PROJECTS")
        claude_history = env("_L_CLAUDE_HISTORY")
        store_root = claude_projects

        conv_check = False
        cwd_slug = workdir.replace("/", "-")
        conv_file = os.path.join(claude_projects, cwd_slug, f"{session_id}.jsonl")

        if not os.path.isfile(conv_file):
            for dirpath, _, _ in os.walk(claude_projects):
                candidate = os.path.join(dirpath, f"{session_id}.jsonl")
                if os.path.isfile(candidate):
                    conv_file = candidate
                    cwd_slug = os.path.basename(dirpath)
                    conv_check = True
                    break
        else:
            conv_check = True

        msg_check = False
        nonce_check = False
        last_user_msg = ""
        confirm_attempts = 0
        matched_after_retry = False
        if conv_check and exit_code == 0:
            probe_text = (message_body or message)[:200]
            required_match = lambda: msg_check and (nonce_check if nonce else True)
            for attempt in range(1, CLAUDE_CONFIRM_ATTEMPTS + 1):
                confirm_attempts = attempt
                last_user_msg = read_last_claude_user_message(conv_file)
                msg_check = bool(last_user_msg and probe_text and probe_text in last_user_msg)
                nonce_check = bool(nonce and last_user_msg and nonce in last_user_msg)
                if required_match():
                    matched_after_retry = attempt > 1
                    break
                if attempt < CLAUDE_CONFIRM_ATTEMPTS:
                    time.sleep(CLAUDE_CONFIRM_SLEEP_SEC)

        session_confirmed = conv_check and msg_check and (nonce_check if nonce else True)
        if header_found:
            session_confirmed = session_confirmed and header_valid
        if session_confirmed:
            confirmation_method = "claude_session_file"
        elif exit_code != 0:
            confirmation_method = "claude_cli_failed"
        else:
            confirmation_method = "unconfirmed"

        pid_check = False
        pid_file = os.path.join(claude_sessions, f"{cli_pid}.json")
        if os.path.isfile(pid_file):
            try:
                with open(pid_file, "r", encoding="utf-8", errors="replace") as f:
                    pid_data = json.loads(f.read())
                if pid_data.get("sessionId") == session_id:
                    pid_check = True
            except (json.JSONDecodeError, KeyError):
                pass

        history_check = False
        if os.path.isfile(claude_history):
            try:
                with open(claude_history, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if obj.get("sessionId") == session_id:
                            history_check = True
                            break
            except (FileNotFoundError, PermissionError):
                pass

        session_file = conv_file if session_confirmed else (conv_file if conv_check else "")
        confirmation = {
            "conversation_file": conv_check,
            "message_match": msg_check,
            "nonce_match": nonce_check if nonce else None,
            "pid_mapping": pid_check,
            "pid_mapping_note": "optional: claude -p may not write sessions/<pid>.json",
            "history_check": history_check,
            "history_check_note": "optional: claude -p may not write to history.jsonl",
            "cwd_slug": cwd_slug,
            "audit_header_found": header_found,
            "audit_header_valid": header_valid if header_found else None,
            "confirmation_method": confirmation_method,
            "match_skipped_due_to_exit_code": exit_code != 0,
            "confirm_attempts": confirm_attempts,
            "matched_after_retry": matched_after_retry,
            "claude_resume_fallback": claude_resume_fallback,
            "claude_resume_fallback_reason": claude_resume_fallback_reason,
            "claude_resume_original_session_id": claude_resume_original_session_id,
            "claude_resume_original_exit_code": claude_resume_original_exit_code,
        }

    elif target == "codex":
        codex_sessions = env("_L_CODEX_SESSIONS")
        store_root = codex_sessions
        codex_procs = int(env("_L_CODEX_PROCS", "0") or "0")
        pre_snapshot = (
            set(env("_L_CODEX_PRE_SNAPSHOT").strip().split("\n"))
            if env("_L_CODEX_PRE_SNAPSHOT").strip()
            else set()
        )

        post_files = set()
        if os.path.isdir(codex_sessions):
            for root, _, files in os.walk(codex_sessions):
                for name in files:
                    if name.endswith(".jsonl"):
                        post_files.add(os.path.join(root, name))

        new_files = sorted(post_files - pre_snapshot)
        nonce_matches = find_codex_nonce_matches(codex_sessions, nonce)
        nonce_new_files = sorted(set(nonce_matches) & set(new_files))

        if nonce_matches:
            if len(nonce_matches) == 1:
                session_file = nonce_matches[0]
                session_id = extract_session_id(session_file)
                session_confirmed = bool(session_id)
                if session_confirmed:
                    confirmation_method = "nonce_unique_match"
            elif len(nonce_new_files) == 1:
                session_file = nonce_new_files[0]
                session_id = extract_session_id(session_file)
                session_confirmed = bool(session_id)
                if session_confirmed:
                    confirmation_method = "nonce_new_file_match"
            else:
                confirmation_method = "nonce_multi_match"
        elif not header_found and len(new_files) == 1:
            session_file = new_files[0]
            session_id = extract_session_id(session_file)
            session_confirmed = bool(session_id)
            if session_confirmed:
                confirmation_method = "legacy_diff"

        if header_found:
            session_confirmed = session_confirmed and header_valid

        confirmation = {
            "pre_count": len(pre_snapshot),
            "post_count": len(post_files),
            "new_count": len(new_files),
            "concurrent_codex_processes": codex_procs,
            "nonce_match_count": len(nonce_matches),
            "nonce_matches": nonce_matches[:5],
            "nonce_new_file_count": len(nonce_new_files),
            "nonce_new_files": nonce_new_files[:5],
            "note": (
                "nonce found in multiple new files; manual verify-rid recommended"
                if confirmation_method == "nonce_multi_match"
                else ""
            ),
            "audit_header_found": header_found,
            "audit_header_valid": header_valid if header_found else None,
            "confirmation_method": confirmation_method,
        }

    verify_commands = build_verify_commands(
        target=target,
        rid=rid,
        nonce=nonce,
        session_id=session_id,
        session_file=session_file,
        store_root=store_root,
    )

    memory_source_files = [
        path for path in env("_L_MEMORY_SOURCE_FILES").split("\n") if path.strip()
    ]
    memory_mirror_generated_at = env("_L_MEMORY_MIRROR_GENERATED_AT")
    audit_record = {
        "timestamp": env("_L_TIMESTAMP"),
        "target": target,
        "rid": rid,
        "nonce": nonce,
        "msg_sha256": msg_sha256,
        "message": message,
        "message_body": message_body,
        "audit_header_found": header_found,
        "audit_header_valid": header_valid if header_found else None,
        "binary_path": env("_L_REAL_BIN"),
        "binary_sha256": env("_L_BIN_HASH"),
        "cli_version": env("_L_BIN_VERSION"),
        "pid": cli_pid,
        "cli_ppid": int(env("_L_CLI_PPID", "0")),
        "cli_start_time": env("_L_CLI_START_TIME"),
        "pre_exec_time": env("_L_PRE_EXEC_TIME"),
        "cwd": workdir,
        "argv": argv,
        "exit_code": exit_code,
        "session_id": session_id,
        "session_source": "launcher_generated" if target == "claude" else "agent_native",
        "session_confirmed": session_confirmed,
        "session_file": session_file,
        "confirmation_method": confirmation_method,
        "confirmation": confirmation,
        "verify_commands": verify_commands,
        "stdout": stdout,
        "stderr": stderr,
        "memory_injected": memory_info["injected"],
        "memory_profile": memory_info["profile"],
        "memory_files": memory_info.get("files", []),
        "memory_source_files": memory_source_files,
        "memory_sha256_claimed": memory_info.get("sha256_claimed", ""),
        "memory_sha256_verified": memory_info.get("sha256_verified", ""),
        "memory_sha256_match": memory_info.get("sha256_match", False),
        "memory_bytes": memory_info["bytes"],
        "memory_mirror_generated_at": memory_mirror_generated_at,
        "meeting_context_injected": meeting_info["injected"],
        "meeting_context_sha256_claimed": meeting_info.get("sha256_claimed", ""),
        "meeting_context_sha256_verified": meeting_info.get("sha256_verified", ""),
        "meeting_context_sha256_match": meeting_info.get("sha256_match", False),
        "meeting_context_bytes": meeting_info.get("bytes", 0),
        "meeting_context_entries": meeting_info.get("entries", 0),
        "meeting_context_untrusted": meeting_info.get("untrusted", False),
        "meeting_context_semantic": meeting_info.get("semantic", ""),
        "meeting_context_mode": meeting_info.get("mode", "full"),
        "sanitizer_mode": env("TRIALOGUE_SANITIZER_MODE", "disabled"),
        "sanitizer_raw_entry_count": int(env("TRIALOGUE_SANITIZER_RAW_COUNT", "0") or 0),
        "sanitizer_injected_entry_count": int(env("TRIALOGUE_SANITIZER_INJECTED_COUNT", "0") or 0),
        "sanitizer_modifications_count": int(env("TRIALOGUE_SANITIZER_MODIFICATIONS", "0") or 0),
        "sanitizer_removed_wrapper_types": [x for x in env("TRIALOGUE_SANITIZER_REMOVED_TYPES", "").split(",") if x],
        "sanitizer_sanitized": env("TRIALOGUE_SANITIZER_SANITIZED", "").lower() == "true",
        "version_gate_policy": env("TRIALOGUE_VERSION_GATE_POLICY", "disabled"),
        "version_gate_allowed": env("TRIALOGUE_VERSION_GATE_ALLOWED", "").lower() != "false",
        "version_gate_reason": env("TRIALOGUE_VERSION_GATE_REASON", ""),
        "version_recheck_policy": env("TRIALOGUE_VERSION_RECHECK_POLICY", "disabled"),
        "version_recheck_allowed": env("TRIALOGUE_VERSION_RECHECK_ALLOWED", "").lower() != "false",
        "version_recheck_result": env("TRIALOGUE_VERSION_RECHECK_RESULT", "disabled"),
        "version_recheck_reason": env("TRIALOGUE_VERSION_RECHECK_REASON", ""),
        "version_recheck_changed_fields": [x for x in env("TRIALOGUE_VERSION_RECHECK_CHANGED_FIELDS", "").split(",") if x],
        "version_startup_snapshot": {
            "binary_path": env("TRIALOGUE_VERSION_STARTUP_BINARY_PATH", ""),
            "binary_sha256": env("TRIALOGUE_VERSION_STARTUP_BINARY_SHA256", ""),
            "cli_version": env("TRIALOGUE_VERSION_STARTUP_CLI_VERSION", ""),
        },
        "version_invocation_snapshot": {
            "binary_path": env("TRIALOGUE_VERSION_INVOCATION_BINARY_PATH", ""),
            "binary_sha256": env("TRIALOGUE_VERSION_INVOCATION_BINARY_SHA256", ""),
            "cli_version": env("TRIALOGUE_VERSION_INVOCATION_CLI_VERSION", ""),
            "snapshot_mode": env("TRIALOGUE_VERSION_INVOCATION_SNAPSHOT_MODE", "missing"),
        },
        "target_context_injected": target_info["injected"],
        "target_name": target_name_env,
        "target_source": target_source_env,
        "target_path": target_path_env,
        "target_cwd_override": target_cwd_override,
        "target_context_claimed_name": target_info.get("name", ""),
        "target_context_claimed_source": target_info.get("source", ""),
        "target_context_claimed_path": target_info.get("path", ""),
        "target_context_sha256_claimed": target_info.get("sha256_claimed", ""),
        "target_context_sha256_verified": target_info.get("sha256_verified", ""),
        "target_context_sha256_match": target_info.get("sha256_match", False),
        "target_context_env_match": target_env_match,
        "claude_resume_fallback": claude_resume_fallback,
        "claude_resume_fallback_reason": claude_resume_fallback_reason,
        "claude_resume_original_session_id": claude_resume_original_session_id,
        "claude_resume_original_exit_code": claude_resume_original_exit_code,
    }

    audit_log = env("_L_AUDIT_LOG")
    try:
        with open(audit_log, "a", encoding="utf-8") as f:
            f.write(json.dumps(audit_record, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"审计日志写入失败: {e}", file=sys.stderr)
        return 1

    meta_file = env("_L_META_FILE")
    if meta_file:
        meta = {
            "rid": rid,
            "nonce": nonce,
            "msg_sha256": msg_sha256,
            "session_id": session_id,
            "session_confirmed": session_confirmed,
            "session_file": session_file,
            "confirmation_method": confirmation_method,
            "exit_code": exit_code,
            "resume_command": verify_commands["resume_command"],
            "verify_rid_command": verify_commands["verify_rid_command"],
            "verify_file_command": verify_commands["verify_file_command"],
            "verify_store_command": verify_commands["verify_store_command"],
            "memory_injected": memory_info["injected"],
            "memory_profile": memory_info["profile"],
            "memory_files": memory_info.get("files", []),
            "memory_source_files": memory_source_files,
            "memory_sha256_claimed": memory_info.get("sha256_claimed", ""),
            "memory_sha256_verified": memory_info.get("sha256_verified", ""),
            "memory_sha256_match": memory_info.get("sha256_match", False),
            "memory_bytes": memory_info["bytes"],
            "memory_mirror_generated_at": memory_mirror_generated_at,
            "meeting_context_injected": meeting_info["injected"],
            "meeting_context_sha256_claimed": meeting_info.get("sha256_claimed", ""),
            "meeting_context_sha256_verified": meeting_info.get("sha256_verified", ""),
            "meeting_context_sha256_match": meeting_info.get("sha256_match", False),
            "meeting_context_bytes": meeting_info.get("bytes", 0),
            "meeting_context_entries": meeting_info.get("entries", 0),
            "meeting_context_untrusted": meeting_info.get("untrusted", False),
            "meeting_context_semantic": meeting_info.get("semantic", ""),
            "meeting_context_mode": meeting_info.get("mode", "full"),
            "sanitizer_mode": env("TRIALOGUE_SANITIZER_MODE", "disabled"),
            "sanitizer_raw_entry_count": int(env("TRIALOGUE_SANITIZER_RAW_COUNT", "0") or 0),
            "sanitizer_injected_entry_count": int(env("TRIALOGUE_SANITIZER_INJECTED_COUNT", "0") or 0),
            "sanitizer_modifications_count": int(env("TRIALOGUE_SANITIZER_MODIFICATIONS", "0") or 0),
            "sanitizer_removed_wrapper_types": [x for x in env("TRIALOGUE_SANITIZER_REMOVED_TYPES", "").split(",") if x],
            "sanitizer_sanitized": env("TRIALOGUE_SANITIZER_SANITIZED", "").lower() == "true",
            "version_gate_policy": env("TRIALOGUE_VERSION_GATE_POLICY", "disabled"),
            "version_gate_allowed": env("TRIALOGUE_VERSION_GATE_ALLOWED", "").lower() != "false",
            "version_gate_reason": env("TRIALOGUE_VERSION_GATE_REASON", ""),
            "version_recheck_policy": env("TRIALOGUE_VERSION_RECHECK_POLICY", "disabled"),
            "version_recheck_allowed": env("TRIALOGUE_VERSION_RECHECK_ALLOWED", "").lower() != "false",
            "version_recheck_result": env("TRIALOGUE_VERSION_RECHECK_RESULT", "disabled"),
            "version_recheck_reason": env("TRIALOGUE_VERSION_RECHECK_REASON", ""),
            "version_recheck_changed_fields": [x for x in env("TRIALOGUE_VERSION_RECHECK_CHANGED_FIELDS", "").split(",") if x],
            "version_startup_snapshot": {
                "binary_path": env("TRIALOGUE_VERSION_STARTUP_BINARY_PATH", ""),
                "binary_sha256": env("TRIALOGUE_VERSION_STARTUP_BINARY_SHA256", ""),
                "cli_version": env("TRIALOGUE_VERSION_STARTUP_CLI_VERSION", ""),
            },
            "version_invocation_snapshot": {
                "binary_path": env("TRIALOGUE_VERSION_INVOCATION_BINARY_PATH", ""),
                "binary_sha256": env("TRIALOGUE_VERSION_INVOCATION_BINARY_SHA256", ""),
                "cli_version": env("TRIALOGUE_VERSION_INVOCATION_CLI_VERSION", ""),
                "snapshot_mode": env("TRIALOGUE_VERSION_INVOCATION_SNAPSHOT_MODE", "missing"),
            },
            "target_context_injected": target_info["injected"],
            "target_name": target_name_env,
            "target_source": target_source_env,
            "target_path": target_path_env,
            "target_cwd_override": target_cwd_override,
            "target_context_claimed_name": target_info.get("name", ""),
            "target_context_claimed_source": target_info.get("source", ""),
            "target_context_claimed_path": target_info.get("path", ""),
            "target_context_sha256_claimed": target_info.get("sha256_claimed", ""),
            "target_context_sha256_verified": target_info.get("sha256_verified", ""),
            "target_context_sha256_match": target_info.get("sha256_match", False),
            "target_context_env_match": target_env_match,
            "claude_resume_fallback": claude_resume_fallback,
            "claude_resume_fallback_reason": claude_resume_fallback_reason,
            "claude_resume_original_session_id": claude_resume_original_session_id,
            "claude_resume_original_exit_code": claude_resume_original_exit_code,
        }
        try:
            with open(meta_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"元数据文件写入失败: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
