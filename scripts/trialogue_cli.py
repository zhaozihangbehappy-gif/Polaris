#!/usr/bin/env python3
"""
OpenClaw Trialogue CLI v4 — 独立 tmux session 版

每个 agent 一个独立的 tmux session，互不干扰：
  tmux attach -t openclaw-claude    ← 一个终端看 Claude TUI
  tmux attach -t openclaw-codex     ← 另一个终端看 Codex TUI

发消息时：退出 TUI → claude -p 取响应 → 重启 TUI（带完整对话）

用法:
  trialogue_cli.py init --topic "主题"
  trialogue_cli.py send -t claude -m "你好"
  trialogue_cli.py send -t all -m "大家说"
  trialogue_cli.py info
  trialogue_cli.py end
"""

import os
import sys
import re
import json
import uuid
import shutil
import subprocess
import threading
import datetime
import time
import argparse
from pathlib import Path

STATE_DIR = Path.home() / ".openclaw" / "bridge"
STATE_FILE = STATE_DIR / "state.json"
WORKSPACE = Path.home() / ".openclaw" / "workspace"

# 每个 agent 一个独立 tmux session
TMUX_CLAUDE = "openclaw-claude"
TMUX_CODEX = "openclaw-codex"


# ═══════════════════════════════════════════════════════════
#  tmux 基础操作
# ═══════════════════════════════════════════════════════════

def _tmux(*args):
    r = subprocess.run(["tmux"] + list(args), capture_output=True, text=True, timeout=10)
    return r.stdout.strip(), r.returncode


def _session_exists(name):
    _, rc = _tmux("has-session", "-t", name)
    return rc == 0


def _create_agent_session(session_name):
    """创建一个 agent 的独立 tmux session，返回 pane_id"""
    if _session_exists(session_name):
        _tmux("kill-session", "-t", session_name)

    _tmux("new-session", "-d", "-s", session_name, "-x", "200", "-y", "50")
    # 开启鼠标
    _tmux("set-option", "-t", session_name, "mouse", "on")
    out, _ = _tmux("list-panes", "-t", session_name, "-F", "#{pane_id}")
    pane_id = out.strip().split("\n")[0]

    # 初始化 shell
    _tmux("send-keys", "-t", pane_id, "export NO_COLOR=1", "Enter")
    _tmux("send-keys", "-t", pane_id, f"cd {WORKSPACE}", "Enter")
    time.sleep(0.3)

    return pane_id


def _wait_for_shell(pane_id, timeout=15):
    """等 pane 里出现 shell prompt ($)"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        content, _ = _tmux("capture-pane", "-t", pane_id, "-p")
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if lines and lines[-1].endswith("$"):
            return True
        time.sleep(0.5)
    return False


def _start_claude_tui(pane_id, sid):
    _tmux("send-keys", "-t", pane_id,
          f"cd {WORKSPACE} && claude --resume {sid}", "Enter")


def _start_codex_tui(pane_id, sid):
    if sid:
        _tmux("send-keys", "-t", pane_id,
              f"cd {WORKSPACE} && codex resume {sid}", "Enter")


# ═══════════════════════════════════════════════════════════
#  状态 / 记录 / catch-up
# ═══════════════════════════════════════════════════════════

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return None


def save_state(state):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


class Transcript:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, name, text):
        t = datetime.datetime.now().strftime("%H:%M:%S")
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"\n**[{t}] {name}:**\n{text}\n")


def build_catchup(state, target, user_text):
    history = state.get("history", [])
    last_seen = state.get(f"{target}_seen", len(history))
    gap_msgs = history[last_seen:]

    parts = []
    if gap_msgs:
        parts.append("══ 你上次发言后的群聊动态 ══")
        for entry in gap_msgs:
            show = entry["text"] if len(entry["text"]) < 600 else entry["text"][:600] + "…"
            parts.append(f"[{entry['time']} {entry['name']}]: {show}")
        parts.append("══════════════════════════════\n")
    parts.append(f"[决策者]: {user_text}")
    return "\n".join(parts)


def _find_codex_sid(text):
    for line in text.split("\n"):
        try:
            obj = json.loads(line.strip())
            for key in ("session_id", "conversation_id", "id"):
                if key in obj and isinstance(obj[key], str):
                    return obj[key]
        except (json.JSONDecodeError, ValueError):
            pass
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)
    return m.group(0) if m else None


# ═══════════════════════════════════════════════════════════
#  核心: 直接在 TUI 里打字，capture-pane 抓响应
#  TUI 全程不退出
# ═══════════════════════════════════════════════════════════

def _send_to_tui(pane_id, message, timeout=300):
    """
    直接在 TUI 里输入消息，等响应完成，capture-pane 复制响应。
    TUI 全程不退出。
    """
    # 1. 发送前快照
    before, _ = _tmux("capture-pane", "-t", pane_id, "-p")

    # 2. 直接在 TUI 里打字
    # 用 load-buffer + paste-buffer 处理长消息，避免 send-keys 的长度/特殊字符问题
    flat = message.replace("\n", "  ")  # TUI 输入框不支持换行，flatten
    buf_file = STATE_DIR / "tmux-paste.txt"
    buf_file.write_text(flat, encoding="utf-8")
    _tmux("load-buffer", str(buf_file))
    _tmux("paste-buffer", "-t", pane_id, "-d")  # -d 粘贴后删 buffer
    time.sleep(0.3)
    _tmux("send-keys", "-t", pane_id, "Enter")

    # 3. 等响应完成：屏幕内容连续 5 秒不变 = 完成
    time.sleep(3)  # 先等处理启动
    prev = None
    stable = 0
    deadline = time.time() + timeout

    while time.time() < deadline:
        current, _ = _tmux("capture-pane", "-t", pane_id, "-p")
        if current == prev:
            stable += 1
            if stable >= 3:  # 6 秒无变化
                break
        else:
            stable = 0
            prev = current
        time.sleep(2)

    # 4. 复制粘贴：capture-pane 拿到屏幕内容
    after, _ = _tmux("capture-pane", "-t", pane_id, "-p")

    # 5. 提取新增内容（before 里没有的行）
    before_lines = before.strip().split("\n")
    after_lines = after.strip().split("\n")

    # 用有序 diff：找 after 中新出现的内容
    # 从 after 末尾往前找，跳过空行和已有行
    before_set = set(l.strip() for l in before_lines if l.strip())
    new_lines = []
    for line in after_lines:
        stripped = line.strip()
        if stripped and stripped not in before_set:
            new_lines.append(stripped)

    response = "\n".join(new_lines).strip()

    # 兜底：如果 diff 没抓到东西，直接返回当前屏幕内容
    if not response:
        response = "\n".join(l for l in after_lines if l.strip()).strip()

    return response or "[响应已显示在 TUI 中]"


# ═══════════════════════════════════════════════════════════
#  init
# ═══════════════════════════════════════════════════════════

def cmd_init(args):
    context = ""
    if args.context:
        p = Path(args.context)
        if p.exists():
            context = p.read_text(encoding="utf-8")
        else:
            print(f"[警告] 背景文档不存在: {p}")

    today = datetime.date.today().isoformat()
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", args.topic).strip("-")
    meeting_dir = Path.home() / ".openclaw" / "meetings" / f"{today}-{slug}"
    meeting_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = str(meeting_dir / "transcript.md")

    for sub in ["claude", "codex"]:
        (STATE_DIR / sub).mkdir(parents=True, exist_ok=True)

    state = {
        "topic": args.topic,
        "created": datetime.datetime.now().isoformat(),
        "transcript": transcript_path,
        "meeting_dir": str(meeting_dir),
        "history": [],
        "claude_sid": None, "claude_ok": False, "claude_seen": 0, "claude_pane": None,
        "codex_sid": None, "codex_ok": False, "codex_seen": 0, "codex_pane": None,
        "send_counter": 0,
    }

    out = []
    out.append("══ 三方会谈初始化 (独立 TUI) ══")
    out.append(f"主题: {args.topic}")
    out.append("")

    # ── Claude ──
    if shutil.which("claude"):
        claude_sid = str(uuid.uuid4())
        out.append("Claude 初始化中...")

        role = (
            f"你在一个三方群聊会议中。主题: {args.topic}\n"
            f"参与者: 决策者（人类，最终决策）、Claude（你，技术实现）、Codex（技术审计）\n"
            f"规则: 简洁回复像聊天，可以反驳别人，中文为主，被指派任务时认真执行并汇报。"
        )
        first = "群聊已建立。请回复「已就绪」确认你在线。"
        if context:
            first = f"以下是本次会议的背景材料:\n\n{context[:4000]}\n\n请阅读后回复「已就绪」。"

        cmd = [
            "claude", "-p",
            "--session-id", claude_sid,
            "--name", f"会谈-{args.topic}",
            "--append-system-prompt", role,
            "--output-format", "text",
            first,
        ]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                stdin=subprocess.DEVNULL, cwd=str(WORKSPACE),
                env={**os.environ, "NO_COLOR": "1"},
            )
            if r.returncode == 0:
                state["claude_sid"] = claude_sid
                state["claude_ok"] = True
                # 创建独立 tmux session + 启动 TUI
                claude_pane = _create_agent_session(TMUX_CLAUDE)
                state["claude_pane"] = claude_pane
                _start_claude_tui(claude_pane, claude_sid)
                out.append(f"✓ Claude 已加入")
                out.append(f"  session: {claude_sid}")
                out.append(f"  TUI: tmux attach -t {TMUX_CLAUDE}")
            else:
                out.append(f"✗ Claude 初始化失败: {r.stderr.strip()[:200]}")
        except subprocess.TimeoutExpired:
            out.append("✗ Claude 初始化超时")
        except Exception as e:
            out.append(f"✗ Claude 错误: {e}")
    else:
        out.append("✗ Claude: CLI 未安装")

    out.append("")

    # ── Codex ──
    if shutil.which("codex"):
        out.append("Codex 初始化中...")
        codex_first = (
            f"你在一个三方群聊会议中。主题: {args.topic}\n"
            f"参与者: 决策者（人类）、Claude（技术实现）、Codex（你，技术审计）\n"
            f"规则: 简洁回复像聊天，可以反驳别人，中文为主，被指派任务时认真执行。\n\n"
        )
        if context:
            codex_first += f"背景材料:\n{context[:4000]}\n\n"
        codex_first += "群聊已建立。请回复「已就绪」确认你在线。"

        cmd = ["codex", "exec"]
        if args.codex_model:
            cmd += ["-m", args.codex_model]
        cmd.append(codex_first)

        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                stdin=subprocess.DEVNULL, cwd=str(WORKSPACE),
            )
            codex_sid = _find_codex_sid(r.stderr + "\n" + r.stdout)
            state["codex_sid"] = codex_sid
            state["codex_ok"] = True
            # 创建独立 tmux session + 启动 TUI
            codex_pane = _create_agent_session(TMUX_CODEX)
            state["codex_pane"] = codex_pane
            _start_codex_tui(codex_pane, codex_sid)
            out.append(f"✓ Codex 已加入")
            if codex_sid:
                out.append(f"  session: {codex_sid}")
            out.append(f"  TUI: tmux attach -t {TMUX_CODEX}")
        except subprocess.TimeoutExpired:
            out.append("✗ Codex 初始化超时")
        except Exception as e:
            out.append(f"✗ Codex 错误: {e}")
    else:
        out.append("✗ Codex: CLI 未安装")

    out.append("")
    out.append(f"会议记录: {transcript_path}")
    out.append("")
    out.append("打开 TUI（各开一个终端）:")
    out.append(f"  tmux attach -t {TMUX_CLAUDE}")
    out.append(f"  tmux attach -t {TMUX_CODEX}")
    out.append("══════════════════════════════════")

    # transcript 头
    with open(transcript_path, "w", encoding="utf-8") as f:
        f.write(f"# 三方会谈: {args.topic}\n\n**日期**: {today}\n\n")
        f.write("## Session 信息\n\n")
        if state["claude_ok"]:
            f.write(f"- **Claude**: `cd ~/.openclaw/workspace && claude --resume {state['claude_sid']}`\n")
            f.write(f"- **Claude TUI**: `tmux attach -t {TMUX_CLAUDE}`\n")
        if state["codex_ok"] and state["codex_sid"]:
            f.write(f"- **Codex**: `codex resume {state['codex_sid']}`\n")
            f.write(f"- **Codex TUI**: `tmux attach -t {TMUX_CODEX}`\n")
        f.write("\n---\n\n## 对话记录\n")

    save_state(state)
    print("\n".join(out))


# ═══════════════════════════════════════════════════════════
#  send
# ═══════════════════════════════════════════════════════════

def cmd_send(args):
    state = load_state()
    if not state:
        print("[错误] 会议未初始化。先运行: trialogue_cli.py init --topic '主题'")
        sys.exit(1)

    message = args.message
    targets = []
    if args.target == "all":
        if state["claude_ok"]: targets.append("claude")
        if state["codex_ok"]: targets.append("codex")
    elif args.target == "claude":
        if not state["claude_ok"]:
            print("[错误] Claude 不可用"); sys.exit(1)
        targets.append("claude")
    elif args.target == "codex":
        if not state["codex_ok"]:
            print("[错误] Codex 不可用"); sys.exit(1)
        targets.append("codex")

    if not targets:
        print("[错误] 没有可用的 agent"); sys.exit(1)

    # 确保 tmux session 还在
    for target in targets:
        tmux_name = TMUX_CLAUDE if target == "claude" else TMUX_CODEX
        if not _session_exists(tmux_name):
            # 重建 session
            pane_id = _create_agent_session(tmux_name)
            state[f"{target}_pane"] = pane_id
            sid = state.get(f"{target}_sid")
            if target == "claude" and sid:
                _start_claude_tui(pane_id, sid)
            elif target == "codex" and sid:
                _start_codex_tui(pane_id, sid)
            save_state(state)

    state["send_counter"] = state.get("send_counter", 0) + 1
    counter = state["send_counter"]

    t = datetime.datetime.now().strftime("%H:%M:%S")
    state["history"].append({"time": t, "name": "决策者", "text": message})

    transcript = Transcript(state["transcript"])
    transcript.append("决策者", message)

    def _do_send(target):
        prompt = build_catchup(state, target, message)
        pane_id = state.get(f"{target}_pane")
        if not pane_id:
            return f"[错误] {target} 无 pane"

        # 直接在 TUI 里打字，capture-pane 抓响应
        return _send_to_tui(pane_id, prompt)

    if len(targets) == 1:
        target = targets[0]
        name = "Claude" if target == "claude" else "Codex"
        reply = _do_send(target)

        state[f"{target}_seen"] = len(state["history"])
        t2 = datetime.datetime.now().strftime("%H:%M:%S")
        state["history"].append({"time": t2, "name": name, "text": reply})
        state[f"{target}_seen"] = len(state["history"])

        transcript.append(name, reply)
        save_state(state)

        print(f"[{name}]:")
        print(reply)
    else:
        results = {}
        def _worker(target):
            results[target] = _do_send(target)

        threads = []
        for target in targets:
            th = threading.Thread(target=_worker, args=(target,))
            threads.append(th)
            th.start()
        for th in threads:
            th.join()

        parts = []
        for target in targets:
            name = "Claude" if target == "claude" else "Codex"
            reply = results.get(target, "[无回复]")

            state[f"{target}_seen"] = len(state["history"])
            t2 = datetime.datetime.now().strftime("%H:%M:%S")
            state["history"].append({"time": t2, "name": name, "text": reply})
            state[f"{target}_seen"] = len(state["history"])

            transcript.append(name, reply)
            parts.append(f"[{name}]:")
            parts.append(reply)
            parts.append("")

        save_state(state)
        print("\n".join(parts))


# ═══════════════════════════════════════════════════════════
#  info / end
# ═══════════════════════════════════════════════════════════

def cmd_info(args):
    state = load_state()
    if not state:
        print("[无活跃会议]"); return

    lines = [
        "══ 会议信息 ══",
        f"主题: {state['topic']}",
        f"创建: {state['created']}",
        f"记录: {state['transcript']}",
        "",
    ]
    if state["claude_ok"]:
        alive = _session_exists(TMUX_CLAUDE)
        lines.append(f"Claude: session {state['claude_sid']}")
        lines.append(f"  TUI: tmux attach -t {TMUX_CLAUDE} ({'运行中' if alive else '已断开'})")
    if state["codex_ok"]:
        alive = _session_exists(TMUX_CODEX)
        sid = state.get('codex_sid') or '(未知)'
        lines.append(f"Codex: session {sid}")
        lines.append(f"  TUI: tmux attach -t {TMUX_CODEX} ({'运行中' if alive else '已断开'})")
    lines += ["", f"历史消息数: {len(state.get('history', []))}", "══════════════"]
    print("\n".join(lines))


def cmd_end(args):
    state = load_state()
    if not state:
        print("[无活跃会议]"); return

    lines = [
        "══ 会议结束 ══",
        f"主题: {state['topic']}",
        f"会议记录: {state['transcript']}",
        "",
        "验证命令:",
    ]
    if state["claude_ok"]:
        lines.append(f"  $ cd ~/.openclaw/workspace && claude --resume {state['claude_sid']}")
    if state["codex_ok"] and state.get("codex_sid"):
        lines.append(f"  $ codex resume {state['codex_sid']}")
    lines += [
        "",
        "TUI session 保留中:",
        f"  $ tmux attach -t {TMUX_CLAUDE}",
        f"  $ tmux attach -t {TMUX_CODEX}",
        "══════════════",
    ]
    print("\n".join(lines))


# ═══════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        prog="trialogue_cli.py",
        description="OpenClaw 三方群聊 — 独立 TUI 版",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="初始化会议")
    p_init.add_argument("--topic", "-t", required=True)
    p_init.add_argument("--context", "-c")
    p_init.add_argument("--claude-model", default="opus")
    p_init.add_argument("--codex-model", default=None)

    p_send = sub.add_parser("send", help="发送消息")
    p_send.add_argument("--target", "-t", required=True, choices=["claude", "codex", "all"])
    p_send.add_argument("--message", "-m", required=True)

    sub.add_parser("info", help="会议信息")
    sub.add_parser("end", help="结束会议")

    args = ap.parse_args()
    {"init": cmd_init, "send": cmd_send, "info": cmd_info, "end": cmd_end}[args.command](args)


if __name__ == "__main__":
    main()
