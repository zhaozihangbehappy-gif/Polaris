"""Codex CLI runner — real subprocess.

Invocation:
  codex exec --json --full-auto --skip-git-repo-check -C <cwd>
             [-c mcp_servers.polaris...] -o <last_msg_file> <prompt>

Parses JSONL from stdout. Event shapes inferred from codex exec --json. Keys
that aren't observed in a given run stay None rather than being fabricated.

PRECONDITION: ~/.codex/config.toml must NOT have other MCP servers configured
(would contaminate baseline runs). v1 assumes a clean config.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from eval.metrics import RunMetrics
from eval.runners._common import (
    codex_mcp_overrides,
    count_redundant_tool_calls,
    find_root_cause_round,
    run_fix_command,
)
from eval.runners.base import Case, Runner, RunResult


class CodexRunner(Runner):
    name = "codex"

    def run(self, case: Case, polaris_enabled: bool, seed: int) -> RunResult:
        if case.workdir:
            cwd = Path(case.workdir)
        else:
            digits = "".join(c for c in case.case_id.split("_")[1] if c.isdigit())
            cwd = Path(f"/tmp/_polaris_case{int(digits):02d}")

        last_msg_file = Path(tempfile.mkstemp(prefix="codex_lastmsg_", suffix=".txt")[1])
        cmd = [
            "codex", "exec",
            "--json",
            "--full-auto",
            "--skip-git-repo-check",
            "-c", 'approval_policy="never"',
            "-C", str(cwd),
            *codex_mcp_overrides(polaris_enabled),
            "-o", str(last_msg_file),
            case.initial_prompt,
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=case.max_rounds * 60,
            )
        except subprocess.TimeoutExpired as e:
            metrics = RunMetrics(
                rounds_to_root_cause=None,
                redundant_actions_count=0,
                token_consumption=0,
                tool_calls=0,
                ci_pass=False,
                human_intervention_count=0,
            )
            return RunResult(
                runner_name=self.name, case_id=case.case_id,
                polaris_enabled=polaris_enabled, metrics=metrics,
                transcript=f"[codex timeout] {e}", seed=seed,
            )

        assistant_texts: list[str] = []
        tool_call_sigs: list[tuple[str, str]] = []
        input_tokens = 0
        output_tokens = 0
        tool_calls = 0

        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            et = ev.get("type", "")
            item = ev.get("item") or {}
            it = item.get("type", "") if isinstance(item, dict) else ""
            if et == "item.completed" and it == "agent_message":
                text = item.get("text", "")
                if isinstance(text, str) and text:
                    assistant_texts.append(text)
            if et == "item.completed" and it == "command_execution":
                tool_call_sigs.append(("shell", json.dumps({"command": item.get("command", "")}, sort_keys=True)))
                tool_calls += 1
            usage = ev.get("usage") or ev.get("token_usage")
            if isinstance(usage, dict):
                input_tokens += int(usage.get("input_tokens", 0) or 0)
                output_tokens += int(usage.get("output_tokens", 0) or 0)

        ci_pass, fix_out = run_fix_command(case.success_criteria["fix_command_test"])
        root_round = find_root_cause_round(
            assistant_texts, case.success_criteria.get("root_cause_regex", "")
        )
        redundant = count_redundant_tool_calls(tool_call_sigs)

        metrics = RunMetrics(
            rounds_to_root_cause=root_round,
            redundant_actions_count=redundant,
            token_consumption=input_tokens + output_tokens,
            tool_calls=tool_calls,
            ci_pass=ci_pass,
            human_intervention_count=0,
        )
        transcript = "\n---\n".join([
            f"[codex exec exit={proc.returncode}]",
            proc.stdout or "",
            f"[stderr]\n{proc.stderr or ''}",
            f"[fix_command_test output]\n{fix_out}",
            f"[last_message_file]\n{last_msg_file.read_text() if last_msg_file.exists() else ''}",
        ])
        return RunResult(
            runner_name=self.name, case_id=case.case_id,
            polaris_enabled=polaris_enabled, metrics=metrics,
            transcript=transcript, seed=seed,
        )
