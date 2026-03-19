#!/usr/bin/env python3
"""
Trialogue v2 — 审计 + session 确认 + 元数据生成
由 launcher.sh 调用，所有输入通过环境变量和文件传递，零 shell 插值。

exit 0 = 审计日志 + 元数据均已写入
exit 1 = 写入失败
"""

import json
import os
import re
import sys


def env(key, default=""):
    return os.environ.get(key, default)


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (FileNotFoundError, PermissionError):
        return ""


def read_last_user_message(conversation_file):
    last_user_msg = ""
    try:
        with open(conversation_file, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "user":
                    continue
                content = obj.get("message", {}).get("content", "")
                if isinstance(content, list):
                    content = " ".join(
                        item.get("text", "") for item in content
                        if isinstance(item, dict)
                    )
                if isinstance(content, str) and content:
                    last_user_msg = content
    except (FileNotFoundError, PermissionError):
        return ""
    return last_user_msg


def confirm_claude_session(session_id, cli_pid, message):
    claude_sessions = env("_L_CLAUDE_SESSIONS")
    claude_projects = env("_L_CLAUDE_PROJECTS")
    claude_history = env("_L_CLAUDE_HISTORY")

    conv_check = False
    actual_cwd = os.getcwd()
    cwd_slug = actual_cwd.replace("/", "-")
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
    if conv_check:
        last_user_msg = read_last_user_message(conv_file)
        msg_substr = message[:200]
        if last_user_msg and msg_substr and msg_substr in last_user_msg:
            msg_check = True

    pid_check = False
    pid_file = os.path.join(claude_sessions, f"{cli_pid}.json")
    if os.path.isfile(pid_file):
        try:
            with open(pid_file, "r", encoding="utf-8") as f:
                pid_data = json.load(f)
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

    confirmation = {
        "conversation_file": conv_check,
        "message_match": msg_check,
        "pid_mapping": pid_check,
        "pid_mapping_note": "optional: claude -p may not write sessions/<pid>.json",
        "history_check": history_check,
        "history_check_note": "optional: claude -p may not write to history.jsonl",
        "cwd_slug": cwd_slug,
    }
    session_confirmed = conv_check and msg_check
    session_file = conv_file if conv_check else ""
    return session_confirmed, session_file, confirmation


def confirm_codex_session():
    codex_sessions = env("_L_CODEX_SESSIONS")
    pre_snapshot_raw = env("_L_CODEX_PRE_SNAPSHOT").strip()
    pre_snapshot = set(pre_snapshot_raw.split("\n")) if pre_snapshot_raw else set()

    post_files = set()
    if os.path.isdir(codex_sessions):
        for root, _, files in os.walk(codex_sessions):
            for name in files:
                if name.endswith(".jsonl"):
                    post_files.add(os.path.join(root, name))

    new_files = sorted(post_files - pre_snapshot)
    new_count = len(new_files)
    session_id = ""
    session_confirmed = False
    session_file = ""

    if new_count == 1:
        session_file = new_files[0]
        match = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4,}-[0-9a-f]{4}-[0-9a-f]{12}",
            os.path.basename(session_file),
        )
        if match:
            session_id = match.group(0)
            session_confirmed = True

    confirmation = {
        "pre_count": len(pre_snapshot),
        "post_count": len(post_files),
        "new_count": new_count,
    }
    return session_id, session_confirmed, session_file, confirmation


def build_argv(target, bin_path, session_id, message):
    if target == "claude":
        return [bin_path, "-p", "--session-id", session_id, "--output-format", "text", message]
    return [bin_path, "exec", message]


def write_json_line(path, payload):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_json_file(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def main():
    target = env("_L_TARGET")
    session_id = env("_L_SESSION_ID")
    cli_pid = int(env("_L_CLI_PID", "0"))
    exit_code = int(env("_L_EXIT_CODE", "1"))
    message = read_file(env("_L_MESSAGE_FILE"))
    stdout = read_file(env("_L_STDOUT_FILE"))
    stderr = read_file(env("_L_STDERR_FILE"))
    bin_path = env("_L_BIN")

    if target == "claude":
        session_confirmed, session_file, confirmation = confirm_claude_session(
            session_id, cli_pid, message
        )
    elif target == "codex":
        session_id, session_confirmed, session_file, confirmation = confirm_codex_session()
    else:
        print(f"未知 target: {target}", file=sys.stderr)
        return 1

    audit_record = {
        "timestamp": env("_L_TIMESTAMP"),
        "target": target,
        "binary_path": env("_L_REAL_BIN"),
        "binary_sha256": env("_L_BIN_HASH"),
        "cli_version": env("_L_BIN_VERSION"),
        "pid": cli_pid,
        "cli_ppid": int(env("_L_CLI_PPID", "0")),
        "cli_start_time": env("_L_CLI_START_TIME"),
        "pre_exec_time": env("_L_PRE_EXEC_TIME"),
        "argv": build_argv(target, bin_path, session_id, message),
        "message": message,
        "exit_code": exit_code,
        "session_id": session_id,
        "session_source": "launcher_generated" if target == "claude" else "agent_native",
        "session_confirmed": session_confirmed,
        "session_file": session_file,
        "confirmation": confirmation,
        "stdout": stdout,
        "stderr": stderr,
    }

    audit_log = env("_L_AUDIT_LOG")
    try:
        write_json_line(audit_log, audit_record)
    except Exception as exc:
        print(f"审计日志写入失败: {exc}", file=sys.stderr)
        return 1

    meta_file = env("_L_META_FILE")
    if meta_file:
        meta = {
            "session_id": session_id,
            "session_confirmed": session_confirmed,
            "exit_code": exit_code,
        }
        try:
            write_json_file(meta_file, meta)
        except Exception as exc:
            print(f"元数据文件写入失败: {exc}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
