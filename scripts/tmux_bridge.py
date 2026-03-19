#!/usr/bin/env python3
"""
OpenClaw tmux Bridge — 实时透明的 Agent 通信层

每个 agent 运行在独立的 tmux pane 中，所有 CLI 调用在 pane 内实时可见。
用户随时可以 `tmux attach -t openclaw-trialogue` 查看每个 agent 的完整交互历史。

IPC 机制：文件交换（inbox → agent CLI → outbox），无黑盒。
"""

import os
import re
import json
import time
import shutil
import subprocess
from pathlib import Path


BRIDGE_DIR = Path.home() / ".openclaw" / "bridge"
TMUX_SESSION = "openclaw-trialogue"


def _tmux(*args, capture=False):
    """执行 tmux 命令"""
    cmd = ["tmux"] + list(args)
    if capture:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip(), r.returncode
    else:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return "", r.returncode


def _session_exists():
    _, rc = _tmux("has-session", "-t", TMUX_SESSION, capture=True)
    return rc == 0


def _pane_shell_ready(pane_id, timeout=5):
    """等待 pane 里的 shell prompt 出现"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        out, _ = _tmux("capture-pane", "-t", pane_id, "-p", capture=True)
        # 只要最后一行有 $ 或 > 就认为 shell 就绪
        lines = [l for l in out.split("\n") if l.strip()]
        if lines and (lines[-1].strip().endswith("$") or lines[-1].strip().endswith(">")):
            return True
        time.sleep(0.3)
    return True  # 超时也继续，不阻塞


class AgentPaneBase:
    """tmux pane 中运行的 agent 基类"""

    def __init__(self, name, pane_id):
        self.name = name
        self.pane_id = pane_id
        self.msg_dir = BRIDGE_DIR / name.lower()
        self.msg_dir.mkdir(parents=True, exist_ok=True)
        self.counter = 0
        self.seen = 0  # transcript 中已看到的消息索引（兼容 trialogue）

    def _inbox_path(self):
        return self.msg_dir / f"msg-{self.counter:04d}.txt"

    def _outbox_path(self):
        return self.msg_dir / f"resp-{self.counter:04d}.txt"

    def _done_path(self):
        return self.msg_dir / f"done-{self.counter:04d}"

    def _clean_old_files(self):
        """清理上一轮的文件"""
        for f in [self._inbox_path(), self._outbox_path(), self._done_path()]:
            f.unlink(missing_ok=True)

    def _write_inbox(self, message):
        """写消息到 inbox 文件（避免 shell 转义问题）"""
        self._inbox_path().write_text(message, encoding="utf-8")

    def _build_cli_command(self):
        """子类实现：返回在 pane 中执行的 CLI 命令字符串"""
        raise NotImplementedError

    def send(self, message, timeout=300):
        """发消息给 agent，等待回复"""
        self.counter += 1
        self._clean_old_files()
        self._write_inbox(message)

        inbox = self._inbox_path()
        outbox = self._outbox_path()
        done = self._done_path()

        # 构建在 pane 里执行的命令
        cli_cmd = self._build_cli_command()
        # 完整命令：读取 inbox → 调用 CLI → 写入 outbox → 标记 done
        shell_cmd = (
            f'{cli_cmd} "$(cat {inbox})" > {outbox} 2>&1; '
            f'touch {done}'
        )

        # 注入到 tmux pane
        _tmux("send-keys", "-t", self.pane_id, shell_cmd, "Enter")

        # 等待 done 标记
        deadline = time.time() + timeout
        while time.time() < deadline:
            if done.exists():
                break
            time.sleep(1)
        else:
            return f"[超时 — {timeout}s 未响应]"

        # 读取响应
        if outbox.exists():
            resp = outbox.read_text(encoding="utf-8").strip()
            return resp or "[空回复]"
        return "[无输出文件]"


class ClaudePane(AgentPaneBase):
    """Claude CLI agent，运行在 tmux pane 中"""

    def __init__(self, pane_id, model="opus"):
        super().__init__("Claude", pane_id)
        self.model = model
        self.sid = None
        self.session_name = ""
        self.ok = shutil.which("claude") is not None

    def init(self, topic, context=""):
        """创建真实的 Claude CLI session"""
        import uuid
        self.sid = str(uuid.uuid4())
        self.session_name = f"会谈-{topic}"

        role = (
            f"你在一个三方群聊会议中。主题: {topic}\n"
            f"参与者: 决策者（人类，最终决策）、Claude（你，技术实现）、Codex（技术审计）\n"
            f"规则: 简洁回复像聊天，可以反驳别人，中文为主，被指派任务时认真执行并汇报。"
        )

        first = "群聊已建立。请回复「已就绪」确认你在线。"
        if context:
            first = f"以下是本次会议的背景材料:\n\n{context[:4000]}\n\n请阅读后回复「已就绪」。"

        # 首次调用：创建 session（在 pane 中执行，用户可见）
        init_msg_file = self.msg_dir / "init-msg.txt"
        init_resp_file = self.msg_dir / "init-resp.txt"
        init_done_file = self.msg_dir / "init-done"

        for f in [init_msg_file, init_resp_file, init_done_file]:
            f.unlink(missing_ok=True)

        init_msg_file.write_text(first, encoding="utf-8")

        # 用 --append-system-prompt 注入角色，用文件避免转义
        role_file = self.msg_dir / "role.txt"
        role_file.write_text(role, encoding="utf-8")

        cmd = (
            f'claude -p'
            f' --session-id {self.sid}'
            f' --name "{self.session_name}"'
            f' --append-system-prompt "$(cat {role_file})"'
            f' --output-format text'
            f' "$(cat {init_msg_file})"'
            f' > {init_resp_file} 2>&1;'
            f' touch {init_done_file}'
        )

        _tmux("send-keys", "-t", self.pane_id, cmd, "Enter")

        # 等待初始化完成
        deadline = time.time() + 120
        while time.time() < deadline:
            if init_done_file.exists():
                return True
            time.sleep(1)
        return False

    def _build_cli_command(self):
        return (
            f'claude -p'
            f' --resume {self.sid}'
            f' --output-format text'
        )

    @property
    def resume_cmd(self):
        return f"cd ~/.openclaw/workspace && claude --resume {self.sid}"


class CodexPane(AgentPaneBase):
    """Codex CLI agent，运行在 tmux pane 中"""

    def __init__(self, pane_id, model=None):
        super().__init__("Codex", pane_id)
        self.model = model
        self.sid = None
        self.ok = shutil.which("codex") is not None

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

        init_msg_file = self.msg_dir / "init-msg.txt"
        init_resp_file = self.msg_dir / "init-resp.txt"
        init_done_file = self.msg_dir / "init-done"

        for f in [init_msg_file, init_resp_file, init_done_file]:
            f.unlink(missing_ok=True)

        init_msg_file.write_text(first, encoding="utf-8")

        model_flag = f' -m {self.model}' if self.model else ''
        cmd = (
            f'codex exec{model_flag}'
            f' "$(cat {init_msg_file})"'
            f' > {init_resp_file} 2>&1;'
            f' touch {init_done_file}'
        )

        _tmux("send-keys", "-t", self.pane_id, cmd, "Enter")

        deadline = time.time() + 120
        while time.time() < deadline:
            if init_done_file.exists():
                # 从输出中提取 session ID
                if init_resp_file.exists():
                    self._find_sid(init_resp_file.read_text(encoding="utf-8"))
                return True
            time.sleep(1)
        return False

    def _build_cli_command(self):
        model_flag = f' -m {self.model}' if self.model else ''
        if self.sid:
            return f'codex exec resume {self.sid}{model_flag}'
        return f'codex exec{model_flag}'

    def send(self, message, timeout=300):
        """重写 send：每次尝试从输出中捕获 session ID"""
        resp = super().send(message, timeout)
        if not self.sid:
            outbox = self._outbox_path()
            if outbox.exists():
                self._find_sid(outbox.read_text(encoding="utf-8"))
        return resp

    def _find_sid(self, text):
        """从 codex 输出中提取 session ID"""
        for line in text.split("\n"):
            try:
                obj = json.loads(line.strip())
                for key in ("session_id", "conversation_id", "id"):
                    if key in obj and isinstance(obj[key], str):
                        self.sid = obj[key]
                        return
            except (json.JSONDecodeError, ValueError):
                pass
        m = re.search(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            text,
        )
        if m:
            self.sid = m.group(0)

    @property
    def resume_cmd(self):
        return f"codex resume {self.sid}" if self.sid else "codex resume --last"


class TmuxBridge:
    """
    管理 tmux session，为每个 agent 创建独立 pane。

    用户随时可以:
      tmux attach -t openclaw-trialogue
    查看所有 agent 的实时 CLI 交互。
    """

    def __init__(self, session_name=TMUX_SESSION):
        self.session_name = session_name
        self.claude = None
        self.codex = None
        self._pane_ids = {}

    def setup(self):
        """创建 tmux session（如不存在）"""
        # 清理旧的 bridge 文件
        if BRIDGE_DIR.exists():
            shutil.rmtree(BRIDGE_DIR)
        BRIDGE_DIR.mkdir(parents=True, exist_ok=True)

        if _session_exists():
            # 杀掉旧 session，重新开始
            _tmux("kill-session", "-t", self.session_name)

        # 创建 session，第一个 pane 给 Claude
        _tmux(
            "new-session", "-d",
            "-s", self.session_name,
            "-n", "agents",
            "-x", "200", "-y", "50",
        )

        # 第一个 pane 的 ID
        out, _ = _tmux(
            "list-panes", "-t", self.session_name,
            "-F", "#{pane_id}", capture=True,
        )
        claude_pane = out.strip().split("\n")[0]
        self._pane_ids["claude"] = claude_pane

        # 设置 pane 标题
        _tmux("select-pane", "-t", claude_pane, "-T", "Claude")

        # 分割出第二个 pane 给 Codex
        _tmux("split-window", "-t", self.session_name, "-h")
        out, _ = _tmux(
            "list-panes", "-t", self.session_name,
            "-F", "#{pane_id}", capture=True,
        )
        pane_ids = out.strip().split("\n")
        codex_pane = [p for p in pane_ids if p != claude_pane][0]
        self._pane_ids["codex"] = codex_pane
        _tmux("select-pane", "-t", codex_pane, "-T", "Codex")

        # 设置环境变量（在 pane 内）
        for pane_id in [claude_pane, codex_pane]:
            _tmux("send-keys", "-t", pane_id, "export NO_COLOR=1", "Enter")
            _tmux("send-keys", "-t", pane_id,
                   f"cd {Path.home() / '.openclaw' / 'workspace'}", "Enter")
            _pane_shell_ready(pane_id)

        return True

    def init_agents(self, topic, context="", claude_model="opus", codex_model=None):
        """初始化两个 agent 的 CLI session"""
        results = {}

        if shutil.which("claude"):
            self.claude = ClaudePane(self._pane_ids["claude"], model=claude_model)
            self.claude.ok = True
            ok = self.claude.init(topic, context)
            results["Claude"] = ok
            if not ok:
                self.claude.ok = False
        else:
            results["Claude"] = False

        if shutil.which("codex"):
            self.codex = CodexPane(self._pane_ids["codex"], model=codex_model)
            self.codex.ok = True
            ok = self.codex.init(topic, context)
            results["Codex"] = ok
            if not ok:
                self.codex.ok = False
        else:
            results["Codex"] = False

        return results

    def get_agent(self, key):
        """根据 key 返回 agent"""
        if key == "claude":
            return self.claude
        elif key == "codex":
            return self.codex
        return None

    @property
    def agents(self):
        """返回 {key: agent} 字典（兼容 trialogue 主循环）"""
        d = {}
        if self.claude:
            d["claude"] = self.claude
        if self.codex:
            d["codex"] = self.codex
        return d

    def attach_cmd(self):
        """返回 attach 命令，供用户在另一个终端使用"""
        return f"tmux attach -t {self.session_name}"

    def cleanup(self):
        """结束会议时清理"""
        if _session_exists():
            _tmux("kill-session", "-t", self.session_name)


if __name__ == "__main__":
    # 快速测试
    print("创建 tmux bridge...")
    bridge = TmuxBridge()
    bridge.setup()
    print(f"tmux session 已创建: {TMUX_SESSION}")
    print(f"查看: {bridge.attach_cmd()}")
    print(f"Panes: {bridge._pane_ids}")
    print("\n按 Enter 清理...")
    input()
    bridge.cleanup()
    print("已清理")
