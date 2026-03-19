#!/usr/bin/env python3
"""
OpenClaw Trialogue v3.0 — 透明可验证的三方群聊

每个 AI 的 session 都是真实的 CLI session，你随时可以在另一个终端
  claude --resume <ID>   或   codex resume <ID>
查看完整对话记录。没有黑盒，每句话都是对应 CLI 真实发出的。

v3.0 新增 --mode tmux: agent 运行在 tmux pane 中，所有 CLI 调用实时可见。
  tmux attach -t openclaw-trialogue  即可实时旁观。

启动:
  python3 trialogue.py --topic "会议主题"
  python3 trialogue.py --topic "会议主题" --mode tmux      # tmux 实时模式
  python3 trialogue.py --topic "Polaris 商业化" --context background.md

群聊:
  @claude / @opus   Claude 回复        /info     Session 信息
  @codex            Codex 回复         /save     保存记录
  @all / @所有人    所有人同时回复     /history  查看历史
  /quit             结束会议
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
import argparse
from pathlib import Path

# 确保 scripts/ 目录在 import 路径中（用于 tmux_bridge）
sys.path.insert(0, str(Path(__file__).resolve().parent))


# ═══════════════════════════════════════════════════════════
#  终端样式
# ═══════════════════════════════════════════════════════════

RST  = "\033[0m"
BOLD = "\033[1m"
DIM  = "\033[2m"

C_USER   = "\033[38;5;114m"    # 绿 — 决策者
C_CLAUDE = "\033[38;5;208m"    # 橙 — Claude
C_CODEX  = "\033[38;5;75m"     # 蓝 — Codex
C_SYS    = "\033[38;5;245m"    # 灰 — 系统
C_ERR    = "\033[38;5;196m"    # 红 — 错误
C_INFO   = "\033[38;5;44m"     # 青 — 信息框
C_LINE   = "\033[38;5;240m"    # 暗线

ROLE_STYLE = {
    "决策者": C_USER,
    "Claude": C_CLAUDE,
    "Codex":  C_CODEX,
    "系统":   C_SYS,
}


def now():
    return datetime.datetime.now().strftime("%H:%M:%S")


def print_msg(name, text):
    """打印一条群聊消息"""
    color = ROLE_STYLE.get(name, C_SYS)
    t = now()
    header = f"{DIM}{t}{RST} {color}{BOLD}{name}{RST}"
    pad = " " * (len(t) + len(name) + 3)
    lines = text.split("\n")
    body = lines[0]
    for line in lines[1:]:
        body += f"\n{pad}{line}"
    print(f"{header}  {body}")


def divider():
    print(f"{C_LINE}{'─' * 60}{RST}")


# ═══════════════════════════════════════════════════════════
#  会议记录（实时追加，崩溃也不丢）
# ═══════════════════════════════════════════════════════════

class Transcript:
    def __init__(self, path):
        self.entries = []       # [(timestamp, name, text), ...]
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, name, text):
        t = now()
        self.entries.append((t, name, text))
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(f"\n**[{t}] {name}:**\n{text}\n")
        return len(self.entries) - 1

    def catchup(self, start, end):
        """格式化 [start, end) 的消息，用于给 agent 补上下文"""
        if start >= end:
            return ""
        lines = []
        for t, name, text in self.entries[start:end]:
            show = text if len(text) < 600 else text[:600] + "…"
            lines.append(f"[{t} {name}]: {show}")
        return "\n".join(lines)

    def write_header(self, topic, session_info):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(f"# 三方会谈: {topic}\n\n")
            f.write(f"**日期**: {datetime.date.today()}\n\n")
            f.write("## Session 信息（可在其他终端 resume 验证）\n\n")
            for name, cmd in session_info.items():
                f.write(f"- **{name}**: `{cmd}`\n")
            f.write("\n---\n\n## 对话记录\n")


# ═══════════════════════════════════════════════════════════
#  Agent: Claude
# ═══════════════════════════════════════════════════════════

class ClaudeAgent:
    def __init__(self, model="opus"):
        self.name = "Claude"
        self.model = model
        self.sid = str(uuid.uuid4())
        self.session_name = ""
        self.ok = shutil.which("claude") is not None
        self.seen = 0           # 在 transcript 中已"看到"的消息索引

    def init(self, topic, context=""):
        """创建真实的 Claude CLI session（带 UUID + 名字）"""
        self.session_name = f"会谈-{topic}"

        role = (
            f"你在一个三方群聊会议中。主题: {topic}\n"
            f"参与者: 决策者（人类，最终决策）、Claude（你，技术实现）、Codex（技术审计）\n"
            f"规则: 简洁回复像聊天，可以反驳别人，中文为主，被指派任务时认真执行并汇报。"
        )

        first = "群聊已建立。请回复「已就绪」确认你在线。"
        if context:
            first = f"以下是本次会议的背景材料:\n\n{context[:4000]}\n\n请阅读后回复「已就绪」。"

        cmd = [
            "claude", "-p",
            "--session-id", self.sid,
            "--name", self.session_name,
            "--append-system-prompt", role,
            "--output-format", "text",
            first,
        ]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                stdin=subprocess.DEVNULL, cwd=str(Path.home()),
                env={**os.environ, "NO_COLOR": "1"},
            )
            return r.returncode == 0
        except Exception:
            return False

    def send(self, message):
        """向 Claude 的真实 session 发一条消息（resume 已有 session）"""
        cmd = [
            "claude", "-p",
            "--resume", self.sid,
            "--output-format", "text",
            message,
        ]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
                stdin=subprocess.DEVNULL, cwd=str(Path.home()),
                env={**os.environ, "NO_COLOR": "1"},
            )
            out = r.stdout.strip()
            if r.returncode != 0 and not out:
                return f"[错误 rc={r.returncode}]: {r.stderr.strip()[:200]}"
            return out or "[空回复]"
        except subprocess.TimeoutExpired:
            return "[超时 — 5 分钟未响应]"
        except Exception as e:
            return f"[调用失败]: {e}"

    @property
    def resume_cmd(self):
        return f"cd ~ && claude --resume {self.sid}"


# ═══════════════════════════════════════════════════════════
#  Agent: Codex
# ═══════════════════════════════════════════════════════════

class CodexAgent:
    def __init__(self, model=None):
        self.name = "Codex"
        self.model = model
        self.sid = None
        self.ok = shutil.which("codex") is not None
        self.seen = 0

    def init(self, topic, context=""):
        """创建真实的 Codex CLI session"""
        first = (
            f"你在一个三方群聊会议中。主题: {topic}\n"
            f"参与者: 决策者（人类）、Claude（技术实现）、Codex（你，技术审计）\n"
            f"规则: 简洁回复像聊天，可以反驳别人，中文为主，被指派任务时认真执行。\n\n"
        )
        if context:
            first += f"背景材料:\n{context[:4000]}\n\n"
        first += "群聊已建立。请回复「已就绪」确认你在线。"

        cmd = ["codex", "exec"]
        if self.model:
            cmd += ["-m", self.model]
        cmd.append(first)

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                               stdin=subprocess.DEVNULL, cwd=str(Path.home()))
            self._find_sid(r.stderr + "\n" + r.stdout)
            return True
        except Exception:
            return False

    def send(self, message):
        """向 Codex 的真实 session 发消息"""
        if self.sid:
            cmd = ["codex", "exec", "resume", self.sid]
        else:
            cmd = ["codex", "exec"]
        if self.model:
            cmd += ["-m", self.model]
        cmd.append(message)

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=300,
                               stdin=subprocess.DEVNULL, cwd=str(Path.home()))
            out = r.stdout.strip()
            if not self.sid:
                self._find_sid(r.stderr + "\n" + r.stdout)
            if r.returncode != 0 and not out:
                return f"[错误 rc={r.returncode}]: {r.stderr.strip()[:200]}"
            return out or "[空回复]"
        except subprocess.TimeoutExpired:
            return "[超时 — 5 分钟未响应]"
        except Exception as e:
            return f"[调用失败]: {e}"

    def _find_sid(self, text):
        """从 codex 输出中提取 session ID"""
        # 尝试 JSONL
        for line in text.split("\n"):
            try:
                obj = json.loads(line.strip())
                for key in ("session_id", "conversation_id", "id"):
                    if key in obj and isinstance(obj[key], str):
                        self.sid = obj[key]
                        return
            except (json.JSONDecodeError, ValueError):
                pass
        # 兜底: UUID 正则
        m = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            text,
        )
        if m:
            self.sid = m.group(0)

    @property
    def resume_cmd(self):
        return f"codex resume {self.sid}" if self.sid else "codex resume --last"


# ═══════════════════════════════════════════════════════════
#  消息路由
# ═══════════════════════════════════════════════════════════

def parse_at(text):
    """解析 @mention，返回目标 key 列表"""
    low = text.lower()
    if "@all" in low or "@所有人" in low:
        return ["claude", "codex"]
    targets = []
    if "@claude" in low or "@opus" in low:
        targets.append("claude")
    if "@codex" in low:
        targets.append("codex")
    return targets


def build_prompt(transcript, agent, user_text, user_idx):
    """构建发给 agent 的完整消息（含群聊动态 catch-up）"""
    gap = transcript.catchup(agent.seen, user_idx)
    parts = []
    if gap:
        parts.append("══ 你上次发言后的群聊动态 ══")
        parts.append(gap)
        parts.append("══════════════════════════════\n")
    parts.append(f"[决策者]: {user_text}")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════
#  主程序
# ═══════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="OpenClaw 三方群聊 — 透明可验证",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python3 trialogue.py --topic '产品评审'\n"
            "  python3 trialogue.py -t '商业化讨论' -c background.md\n"
        ),
    )
    ap.add_argument("--topic", "-t", default="三方会谈", help="会议主题")
    ap.add_argument("--context", help="背景文档路径（会注入到 agent 初始上下文）")
    ap.add_argument("--claude-model", default="opus", help="Claude 模型 (默认 opus)")
    ap.add_argument("--codex-model", default=None, help="Codex 模型")
    ap.add_argument("--mode", choices=["subprocess", "tmux"], default="subprocess",
                    help="通信模式: subprocess (经典) 或 tmux (实时透明)")
    ap.add_argument("--dry-run", action="store_true", help="测试模式，不实际调用 CLI")
    args = ap.parse_args()

    # ── 加载背景文档 ──
    context = ""
    if args.context:
        p = Path(args.context)
        if p.exists():
            context = p.read_text(encoding="utf-8")
        else:
            print(f"{C_ERR}  背景文档不存在: {p}{RST}")

    # ── 会议目录 ──
    today = datetime.date.today().isoformat()
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", args.topic).strip("-")
    meeting_dir = Path.home() / ".openclaw" / "meetings" / f"{today}-{slug}"
    meeting_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = meeting_dir / "transcript.md"
    transcript = Transcript(transcript_path)

    # ── 初始化 agents ──
    use_tmux = args.mode == "tmux"
    tmux_bridge = None

    if use_tmux and not args.dry_run:
        from tmux_bridge import TmuxBridge
        tmux_bridge = TmuxBridge()
        print(f"{DIM}  正在创建 tmux session...{RST}")
        tmux_bridge.setup()
        results = tmux_bridge.init_agents(
            args.topic, context,
            claude_model=args.claude_model,
            codex_model=args.codex_model,
        )
        claude = tmux_bridge.claude
        codex = tmux_bridge.codex
        agents = tmux_bridge.agents
    else:
        claude = ClaudeAgent(model=args.claude_model)
        codex  = CodexAgent(model=args.codex_model)
        agents = {"claude": claude, "codex": codex}

    if not args.dry_run:
        all_ok = any(a and a.ok for a in [claude, codex])
        if not all_ok:
            print(f"{C_ERR}错误: claude 和 codex CLI 都未安装{RST}")
            print(f"{DIM}  需要至少安装一个: claude (Anthropic) 或 codex (OpenAI){RST}")
            sys.exit(1)

    # ── Banner ──
    print()
    print(f"{BOLD}{'═' * 60}{RST}")
    print(f"{BOLD}  OpenClaw 三方会谈{RST}")
    mode_label = "tmux 实时透明" if use_tmux else "subprocess"
    print(f"{DIM}  主题: {args.topic}  |  模式: {mode_label}{RST}")
    if context:
        print(f"{DIM}  背景: 已加载 ({len(context)} 字){RST}")
    print(f"{BOLD}{'═' * 60}{RST}")
    print()

    # ── 创建真实 session（仅 subprocess 模式需要这一步）──
    if not use_tmux and not args.dry_run:
        for agent in [claude, codex]:
            if not agent or not agent.ok:
                name = agent.name if agent else "?"
                print(f"  {C_SYS}✗ {name}: CLI 未安装，跳过{RST}")
                continue
            color = ROLE_STYLE[agent.name]
            print(f"  {color}{DIM}{agent.name} 正在加入...{RST}", end="", flush=True)
            ok = agent.init(args.topic, context)
            if ok:
                print(f"\r  {color}✓ {agent.name} 已加入{' ' * 20}{RST}")
            else:
                print(f"\r  {C_ERR}✗ {agent.name} 加入失败{' ' * 20}{RST}")
                agent.ok = False
        print()
    elif use_tmux and not args.dry_run:
        # tmux 模式下显示初始化结果
        for agent in [claude, codex]:
            if not agent:
                continue
            color = ROLE_STYLE.get(agent.name, C_SYS)
            if agent.ok:
                print(f"  {color}✓ {agent.name} 已加入 (tmux pane){RST}")
            else:
                print(f"  {C_ERR}✗ {agent.name} 加入失败{RST}")
        print()

    # ── Session 信息框（核心：透明可验证）──
    session_info = {}
    print(f"{C_INFO}┌{'─' * 58}┐{RST}")
    if use_tmux:
        print(f"{C_INFO}│{RST} {BOLD}实时透明 — tmux pane 中所有 CLI 调用实时可见{RST}")
        print(f"{C_INFO}│{RST}")
        print(f"{C_INFO}│{RST}  {BOLD}实时旁观:{RST}")
        print(f"{C_INFO}│{RST}    {DIM}$ tmux attach -t openclaw-trialogue{RST}")
    else:
        print(f"{C_INFO}│{RST} {BOLD}透明验证 — 以下 session 可在其他终端随时 resume{RST}")
    print(f"{C_INFO}│{RST}")

    if claude and (claude.ok or args.dry_run):
        print(f"{C_INFO}│{RST}  {C_CLAUDE}{BOLD}Claude{RST}")
        print(f"{C_INFO}│{RST}    ID:  {DIM}{claude.sid}{RST}")
        print(f"{C_INFO}│{RST}    验证: {DIM}$ {claude.resume_cmd}{RST}")
        session_info["Claude"] = claude.resume_cmd

    if codex and (codex.ok or args.dry_run):
        sid_show = codex.sid or "(首次回复后自动获取)"
        print(f"{C_INFO}│{RST}  {C_CODEX}{BOLD}Codex{RST}")
        print(f"{C_INFO}│{RST}    ID:  {DIM}{sid_show}{RST}")
        print(f"{C_INFO}│{RST}    验证: {DIM}$ {codex.resume_cmd}{RST}")
        session_info["Codex"] = codex.resume_cmd

    print(f"{C_INFO}│{RST}")
    print(f"{C_INFO}│{RST}  {DIM}会议记录: {transcript_path}{RST}")
    print(f"{C_INFO}└{'─' * 58}┘{RST}")
    print()

    # 写 transcript 文件头 + session info JSON
    transcript.write_header(args.topic, session_info)
    (meeting_dir / "session-info.json").write_text(
        json.dumps(session_info, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    # ── 快捷键提示 ──
    print(f"  {DIM}@claude    Claude 回复      /info     Session 信息{RST}")
    print(f"  {DIM}@codex     Codex 回复       /save     保存记录{RST}")
    print(f"  {DIM}@all       所有人回复       /history  查看历史{RST}")
    print(f"  {DIM}@所有人    同 @all          /quit     结束会议{RST}")
    print()
    divider()
    print()

    # ═══════════════════════════════════════════════════════
    #  主循环
    # ═══════════════════════════════════════════════════════

    while True:
        try:
            raw = input(f"{C_USER}{BOLD}决策者>{RST} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        # ── 命令处理 ──
        if raw == "/quit":
            break

        if raw == "/info":
            print()
            if use_tmux:
                print(f"  {BOLD}模式: tmux 实时透明{RST}")
                print(f"  {DIM}旁观: $ tmux attach -t openclaw-trialogue{RST}")
                print()
            if claude and claude.ok:
                print(f"  {C_CLAUDE}Claude{RST}: {claude.resume_cmd}")
            if codex and codex.ok:
                resume = codex.resume_cmd
                print(f"  {C_CODEX}Codex{RST}:  {resume}")
            print(f"  {DIM}记录: {transcript_path}{RST}")
            print()
            continue

        if raw.startswith("/save"):
            parts = raw.split(maxsplit=1)
            if len(parts) > 1:
                dst = Path(parts[1])
                shutil.copy(transcript_path, dst)
                print(f"{C_SYS}  已另存到: {dst}{RST}")
            else:
                print(f"{C_SYS}  记录位置: {transcript_path}{RST}")
            continue

        if raw == "/history":
            print()
            divider()
            for t, name, text in transcript.entries:
                color = ROLE_STYLE.get(name, C_SYS)
                short = text if len(text) < 120 else text[:120] + "…"
                print(f"  {DIM}{t}{RST} {color}{name}{RST}: {short}")
            divider()
            print()
            continue

        # ── 显示并记录用户消息 ──
        print_msg("决策者", raw)
        user_idx = transcript.add("决策者", raw)

        # ── 解析 @mention ──
        targets = parse_at(raw)
        if not targets:
            print(f"{DIM}  (用 @claude @codex @all 让 AI 回复){RST}")
            print()
            continue

        # 过滤不可用的 agent
        active = []
        for t in targets:
            a = agents.get(t)
            if a and (a.ok or args.dry_run):
                active.append((t, a))
            else:
                name = a.name if a else t
                print(f"  {C_ERR}{name} 不可用，跳过{RST}")

        if not active:
            print()
            continue

        # ── 发送消息 ──

        def _do_send(agent):
            """构建 prompt 并发送"""
            prompt = build_prompt(transcript, agent, raw, user_idx)
            if args.dry_run:
                return f"[dry-run] session={agent.sid or 'N/A'}, 收到 {len(raw)} 字"
            return agent.send(prompt)

        if len(active) == 1:
            # 单目标：显示"思考中"，完成后覆盖
            key, agent = active[0]
            color = ROLE_STYLE[agent.name]
            print(f"  {color}{DIM}{agent.name} 思考中...{RST}", end="", flush=True)
            reply = _do_send(agent)
            print(f"\r{' ' * 50}\r", end="")
            print_msg(agent.name, reply)
            idx = transcript.add(agent.name, reply)
            agent.seen = idx + 1

            # 如果 codex session ID 刚获取到，更新 session info
            if agent.name == "Codex" and codex.sid:
                session_info["Codex"] = codex.resume_cmd
        else:
            # 并行：先显示所有"思考中"，然后同时请求
            for _, agent in active:
                color = ROLE_STYLE[agent.name]
                print(f"  {color}{DIM}{agent.name} 思考中...{RST}")

            results = {}

            def _worker(key, agent):
                try:
                    results[key] = _do_send(agent)
                except Exception as e:
                    results[key] = f"[线程错误]: {e}"

            threads = []
            for key, agent in active:
                th = threading.Thread(target=_worker, args=(key, agent))
                threads.append(th)
                th.start()
            for th in threads:
                th.join()

            # 依次显示结果
            print()
            for key, agent in active:
                reply = results.get(key, "[无回复]")
                print_msg(agent.name, reply)
                idx = transcript.add(agent.name, reply)
                agent.seen = idx + 1

            # 更新 codex session info
            if codex.sid and "Codex" not in session_info:
                session_info["Codex"] = codex.resume_cmd

        print()

    # ═══════════════════════════════════════════════════════
    #  结束
    # ═══════════════════════════════════════════════════════

    divider()
    print(f"{C_SYS}  会议结束{RST}")
    print()
    print(f"  {DIM}会议记录: {transcript_path}{RST}")
    print()
    print(f"  {DIM}随时可在其他终端 resume 查看完整记录:{RST}")
    if claude and claude.ok:
        print(f"  {C_CLAUDE}$ {claude.resume_cmd}{RST}")
    if codex and codex.ok:
        print(f"  {C_CODEX}$ {codex.resume_cmd}{RST}")
    print()

    # tmux 模式清理提示
    if tmux_bridge:
        print(f"  {DIM}tmux session 仍在运行，可继续查看:{RST}")
        print(f"  {DIM}$ tmux attach -t openclaw-trialogue{RST}")
        print(f"  {DIM}要销毁: $ tmux kill-session -t openclaw-trialogue{RST}")
        print()


if __name__ == "__main__":
    main()
