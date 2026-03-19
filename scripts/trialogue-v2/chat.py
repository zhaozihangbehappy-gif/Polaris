#!/usr/bin/env python3
"""
Trialogue v2 — 群聊界面
唯一职责：解析用户输入 + 格式化显示
不接触 session store，不直接调用 agent CLI

输出协议：
  launcher stdout     → 纯 agent 原始输出
  launcher --meta-file → JSON 元数据文件（session_id, session_confirmed）
  launcher stderr     → 错误信息
"""

import os
import sys
import re
import json
import uuid
import subprocess
import argparse
import datetime
import tempfile

# @mention 正则：硬解析，不用 AI 猜
MENTION_RE = re.compile(r"@(claude|codex|all|所有人)", re.IGNORECASE)


def parse_message(text):
    """解析 @mention，返回 (targets, clean_message)"""
    mentions = set()
    for m in MENTION_RE.finditer(text):
        tag = m.group(1).lower()
        if tag in ("all", "所有人"):
            mentions.update(["claude", "codex"])
        else:
            mentions.add(tag)

    clean = MENTION_RE.sub("", text).strip()
    return sorted(mentions), clean if clean else text.strip()


def call_launcher(launcher_path, conf_path, target, message, session_id=None):
    """调用 launcher.sh，返回 (agent_stdout, meta_dict)

    launcher stdout     = 纯 agent 原始输出（不含任何元数据）
    launcher --meta-file = JSON 元数据写入临时文件
    """
    meta_fd, meta_path = tempfile.mkstemp(prefix="trialogue-meta-", suffix=".json")
    os.close(meta_fd)

    cmd = [
        "/bin/bash", "--noprofile", "--norc",
        launcher_path,
        "--target", target,
        "--message", message,
        "--conf", conf_path,
        "--meta-file", meta_path,
    ]
    if session_id:
        cmd.extend(["--session-id", session_id])

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        timeout=300,
    )

    meta = {}
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
            if raw:
                meta = json.loads(raw)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    finally:
        try:
            os.unlink(meta_path)
        except FileNotFoundError:
            pass

    agent_stdout = result.stdout.strip() if result.stdout else ""

    if result.returncode != 0 and not agent_stdout:
        err_lines = [line for line in (result.stderr or "").split("\n") if line]
        agent_stdout = f"[错误] 退出码 {result.returncode}\n" + "\n".join(err_lines)

    return agent_stdout, meta


def main():
    parser = argparse.ArgumentParser(description="Trialogue v2 群聊")
    parser.add_argument("--topic", required=True, help="会议主题")
    parser.add_argument("--launcher", required=True, help="launcher.sh 绝对路径")
    parser.add_argument("--conf", required=True, help="trialogue-v2.conf 绝对路径")
    args = parser.parse_args()

    claude_sid = str(uuid.uuid4())
    codex_sid = None

    now = datetime.datetime.now().strftime("%H:%M:%S")
    print("══ Trialogue v2 ══")
    print(f"主题: {args.topic}")
    print(f"时间: {now}")
    print(f"Claude session: {claude_sid}")
    print()
    print("用法: @claude / @codex / @all + 消息")
    print("输入 /quit 或 /exit 退出")
    print("输入 /info 查看 session 信息")
    print("══════════════════")
    print()

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n群聊结束。")
            break

        if not user_input:
            continue

        if user_input in ("/quit", "/exit", "退出", "结束"):
            print()
            print("══ 群聊结束 ══")
            print("验真命令：")
            print(f"  claude --resume {claude_sid}")
            if codex_sid:
                print(f"  codex resume {codex_sid}")
            print("  cat ~/.openclaw/trialogue/audit.jsonl | jq .")
            print("══════════════")
            break

        if user_input in ("/info", "会议信息"):
            print(f"  主题: {args.topic}")
            print(f"  Claude session: {claude_sid}")
            print(f"  Codex session: {codex_sid or '(未建立)'}")
            print()
            continue

        targets, message = parse_message(user_input)

        if not targets:
            print("  提示: 用 @claude @codex @all 来发消息给 agent")
            print()
            continue

        for target in targets:
            name = "Claude" if target == "claude" else "Codex"
            sid = claude_sid if target == "claude" else codex_sid

            print(f"  → 正在调用 {name}...")

            reply, meta = call_launcher(
                args.launcher, args.conf, target, message, session_id=sid
            )

            if target == "codex" and meta.get("session_id"):
                codex_sid = meta["session_id"]

            confirmed = meta.get("session_confirmed", False)
            confirm_tag = "verified" if confirmed else "UNVERIFIED"

            t2 = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"  [{t2} {name}] ({confirm_tag}):")
            print(f"  {reply}")
            print()


if __name__ == "__main__":
    main()
