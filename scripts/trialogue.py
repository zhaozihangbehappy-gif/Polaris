#!/usr/bin/env python3
# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""
Polaris Trialogue — 三方群聊 TUI (CLI 模式，走订阅不花额外钱)

用法:
  python3 scripts/trialogue.py [--context THREEWAY_DISCUSSION_2026-03-18.md]

原理:
  - Claude 侧: 用 `claude -p --resume SESSION_ID` 发消息，走你的 Claude 订阅
  - Codex 侧: 用 `codex exec resume SESSION_ID` 发消息，走你的 Codex 订阅
  - TUI 只是消息路由器，不直接调 API，不花额外钱

群聊规则:
  - @claude / @opus  → Claude 回复
  - @codex           → Codex 回复
  - @all             → 两个都回复
  - /quit            → 退出
  - /history         → 显示完整对话历史
  - /clear           → 清除历史（创建新 session）
  - /save [file]     → 保存对话记录
"""

import json
import os
import re
import subprocess
import sys
import datetime
import uuid
import tempfile
from pathlib import Path

# ── 颜色 ──────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    USER   = "\033[38;5;114m"   # 绿色
    CLAUDE = "\033[38;5;208m"   # 橙色
    CODEX  = "\033[38;5;75m"    # 蓝色
    SYS    = "\033[38;5;245m"   # 灰色
    ERR    = "\033[38;5;196m"   # 红色
    SEP    = "\033[38;5;240m"


def styled(color, name, msg):
    timestamp = datetime.datetime.now().strftime("%H:%M")
    header = f"{C.DIM}{timestamp}{C.RESET} {color}{C.BOLD}{name}{C.RESET}"
    indent = " " * (len(timestamp) + len(name) + 3)
    lines = msg.split("\n")
    formatted = lines[0]
    for line in lines[1:]:
        formatted += "\n" + indent + line
    return f"{header}  {formatted}"


def sys_msg(msg):
    print(f"{C.SYS}{'─' * 60}{C.RESET}")
    print(f"{C.SYS}  {msg}{C.RESET}")
    print(f"{C.SYS}{'─' * 60}{C.RESET}")


# ── CLI 检测 ──────────────────────────────────────────

def find_cli(name):
    """检查 CLI 是否可用"""
    try:
        r = subprocess.run(["which", name], capture_output=True, text=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


# ── Agent 会话管理 ────────────────────────────────────

class ClaudeAgent:
    """通过 claude CLI 通信"""

    def __init__(self, model="opus"):
        self.model = model
        self.session_id = None
        self.available = find_cli("claude")

    def send(self, message, is_first=False):
        """发消息并获取回复"""
        cmd = ["claude", "-p", "--model", self.model, "--output-format", "text"]

        if self.session_id and not is_first:
            cmd += ["--resume", self.session_id]
        else:
            # 首次: 生成 session ID
            self.session_id = str(uuid.uuid4())
            cmd += ["--session-id", self.session_id]

        cmd.append(message)

        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180,
                env={**os.environ, "NO_COLOR": "1"}
            )
            reply = r.stdout.strip()
            if r.returncode != 0 and not reply:
                reply = f"[错误 rc={r.returncode}]: {r.stderr.strip()[:300]}"
            return reply or "[空回复]"
        except subprocess.TimeoutExpired:
            return "[超时 — Claude 思考时间超过 3 分钟]"
        except Exception as e:
            return f"[调用失败]: {e}"


class CodexAgent:
    """通过 codex CLI 通信"""

    def __init__(self, model=None):
        self.model = model  # None = use codex default
        self.session_id = None
        self.available = find_cli("codex")

    def send(self, message, is_first=False):
        """发消息并获取回复"""
        if self.session_id and not is_first:
            # resume 模式
            cmd = ["codex", "exec", "resume", self.session_id]
            if self.model:
                cmd += ["-m", self.model]
            cmd += ["--", message]
        else:
            # 首次
            cmd = ["codex", "exec"]
            if self.model:
                cmd += ["-m", self.model]
            cmd += ["--", message]

        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180,
                env={**os.environ, "NO_COLOR": "1"}
            )
            output = r.stdout.strip()

            # 首次调用时尝试从 stderr 或输出中提取 session ID
            if not self.session_id:
                self._try_extract_session_id(r.stderr + "\n" + output)

            if r.returncode != 0 and not output:
                output = f"[错误 rc={r.returncode}]: {r.stderr.strip()[:300]}"
            return output or "[空回复]"
        except subprocess.TimeoutExpired:
            return "[超时 — Codex 思考时间超过 3 分钟]"
        except Exception as e:
            return f"[调用失败]: {e}"

    def _try_extract_session_id(self, text):
        """尝试从输出中提取 session ID"""
        # codex 常在 stderr 输出 session id
        m = re.search(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', text)
        if m:
            self.session_id = m.group(0)


# ── @mention 解析 ─────────────────────────────────────

def parse_mentions(text):
    text_lower = text.lower()
    targets = []
    if "@all" in text_lower or "@所有人" in text_lower:
        targets = ["claude", "codex"]
    else:
        if "@claude" in text_lower or "@opus" in text_lower:
            targets.append("claude")
        if "@codex" in text_lower:
            targets.append("codex")
    return targets


# ── 群聊上下文格式化 ──────────────────────────────────

def format_group_context(transcript_plain, new_message, sender="决策者"):
    """把群聊历史 + 新消息打包成一条 prompt"""
    parts = []
    if transcript_plain:
        parts.append("以下是群聊的历史记录：")
        parts.append("---")
        parts.append("\n".join(transcript_plain[-30:]))  # 最近 30 条
        parts.append("---")
    parts.append(f"\n[{sender}]: {new_message}")
    parts.append("\n请以你的角色（见 system prompt）回复。简洁、直接、像聊天。")
    return "\n".join(parts)


# ── 主循环 ────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Polaris 三方群聊 TUI (CLI 模式)")
    parser.add_argument("--context", type=str,
                        default="THREEWAY_DISCUSSION_2026-03-18.md",
                        help="背景文档路径")
    parser.add_argument("--claude-model", type=str, default="opus",
                        help="Claude 模型 (默认: opus)")
    parser.add_argument("--codex-model", type=str, default=None,
                        help="Codex 模型 (默认: codex 自带默认)")
    args = parser.parse_args()

    # 加载背景文档
    context_text = ""
    ctx_path = Path(args.context)
    if not ctx_path.exists():
        ctx_path = Path(__file__).resolve().parent.parent / args.context
    if ctx_path.exists():
        context_text = ctx_path.read_text(encoding="utf-8")
        sys_msg(f"已加载背景文档: {ctx_path.name} ({len(context_text)} 字)")
    else:
        sys_msg(f"未找到背景文档: {args.context}")

    # 初始化 agents
    claude = ClaudeAgent(model=args.claude_model)
    codex = CodexAgent(model=args.codex_model)

    if not claude.available and not codex.available:
        print(f"{C.ERR}错误: claude 和 codex CLI 都不可用{C.RESET}")
        sys.exit(1)

    # 欢迎
    print()
    print(f"{C.BOLD}{'═' * 60}{C.RESET}")
    print(f"{C.BOLD}  Polaris 三方会谈{C.RESET}")
    print(f"{C.DIM}  决策者 × Claude Opus × Codex{C.RESET}")
    print(f"{C.DIM}  走 CLI 订阅，不花额外钱{C.RESET}")
    print(f"{C.BOLD}{'═' * 60}{C.RESET}")
    print()
    status = lambda name, ok: f"{'在线' if ok else '离线'}"
    print(f"  {C.CLAUDE}Claude: {status('claude', claude.available)}{C.RESET}")
    print(f"  {C.CODEX}Codex:  {status('codex', codex.available)}{C.RESET}")
    print()
    print(f"  {C.SYS}@claude / @opus  → Claude 回复{C.RESET}")
    print(f"  {C.SYS}@codex           → Codex 回复{C.RESET}")
    print(f"  {C.SYS}@all             → 两个都回复{C.RESET}")
    print(f"  {C.SYS}/quit            → 退出{C.RESET}")
    print(f"  {C.SYS}/history         → 查看历史{C.RESET}")
    print(f"  {C.SYS}/save [file]     → 保存对话记录{C.RESET}")
    print()

    # 初始化 sessions — 注入背景文档
    if context_text:
        sys_prompt = f"""你是 Polaris 三方会谈中的一个参与者。这是一个群聊环境，参与者有：
- 决策者（人类，项目所有者）
- Claude Opus（技术实现者，初始商业建议提出者）
- Codex（技术审计者，独立商业评估者）

群聊规则：
1. 只在被 @ 提到时发言
2. 保持简洁，像聊天不像写报告
3. 可以引用或反驳其他参与者的观点
4. 有不同意见直说，不要客气
5. 用中文回复（技术术语可用英文）

以下是会谈的背景文档：

{context_text}

请回复"已就绪"表示你已读完背景文档。"""

        print(f"{C.SYS}  正在初始化 sessions（注入背景文档）...{C.RESET}")

        if claude.available:
            print(f"{C.CLAUDE}{C.DIM}  Claude 读取背景...{C.RESET}", end="", flush=True)
            init_reply = claude.send(sys_prompt, is_first=True)
            print(f"\r{' ' * 50}\r", end="")
            print(styled(C.CLAUDE, "Claude", "已加入会谈"))

        if codex.available:
            print(f"{C.CODEX}{C.DIM}  Codex 读取背景...{C.RESET}", end="", flush=True)
            init_reply = codex.send(sys_prompt, is_first=True)
            print(f"\r{' ' * 50}\r", end="")
            print(styled(C.CODEX, "Codex", "已加入会谈"))

        print()

    # 对话记录
    transcript = []          # 带颜色（显示用）
    transcript_plain = []    # 纯文本（传给 agent 用）

    while True:
        try:
            user_input = input(f"{C.USER}{C.BOLD}决策者>{C.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys_msg("会谈结束")
            break

        if not user_input:
            continue

        # 命令处理
        if user_input == "/quit":
            sys_msg("会谈结束")
            break
        elif user_input == "/history":
            print(f"\n{C.SEP}{'─' * 60}{C.RESET}")
            for entry in transcript:
                print(entry)
            print(f"{C.SEP}{'─' * 60}{C.RESET}\n")
            continue
        elif user_input.startswith("/save"):
            parts = user_input.split(maxsplit=1)
            save_path = parts[1] if len(parts) > 1 else f"trialogue_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            try:
                ansi_escape = re.compile(r'\033\[[0-9;]*m')
                clean = [ansi_escape.sub('', e) for e in transcript]
                Path(save_path).write_text("\n\n".join(clean), encoding="utf-8")
                sys_msg(f"已保存到 {save_path}")
            except Exception as e:
                print(f"{C.ERR}保存失败: {e}{C.RESET}")
            continue

        # 显示用户消息
        user_line = styled(C.USER, "决策者", user_input)
        print(user_line)
        transcript.append(user_line)
        transcript_plain.append(f"[决策者]: {user_input}")

        # 解析 mentions
        targets = parse_mentions(user_input)

        if not targets:
            print(f"{C.DIM}  (提示: @claude @codex @all 触发回复){C.RESET}")
            continue

        # 依次调用被 @ 的 agent
        for target in targets:
            if target == "claude":
                if not claude.available:
                    print(styled(C.ERR, "系统", "Claude CLI 不可用"))
                    continue
                prompt = format_group_context(transcript_plain, user_input)
                print(f"{C.CLAUDE}{C.DIM}  Claude 思考中...{C.RESET}", end="", flush=True)
                reply = claude.send(prompt)
                print(f"\r{' ' * 50}\r", end="")
                reply_line = styled(C.CLAUDE, "Claude", reply)
                print(reply_line)
                transcript.append(reply_line)
                transcript_plain.append(f"[Claude]: {reply}")

            elif target == "codex":
                if not codex.available:
                    print(styled(C.ERR, "系统", "Codex CLI 不可用"))
                    continue
                prompt = format_group_context(transcript_plain, user_input)
                print(f"{C.CODEX}{C.DIM}  Codex 思考中...{C.RESET}", end="", flush=True)
                reply = codex.send(prompt)
                print(f"\r{' ' * 50}\r", end="")
                reply_line = styled(C.CODEX, "Codex", reply)
                print(reply_line)
                transcript.append(reply_line)
                transcript_plain.append(f"[Codex]: {reply}")

        print()


if __name__ == "__main__":
    main()
