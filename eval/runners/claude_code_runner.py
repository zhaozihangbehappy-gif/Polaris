# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Claude Code CLI runner — real subprocess.

Invocation:
  claude -p "<prompt>" --output-format stream-json --verbose
         --strict-mcp-config --mcp-config <json_file>
         --add-dir <case_cwd>

stream-json event shapes (observed):
  system/init, system/api_retry, rate_limit_event,
  assistant { message: { content: [{type:text,text}], usage: {...} } },
  result  { num_turns, total_cost_usd, usage, result, is_error }

Rate-limit handling: if a rate_limit_event with status != "allowed" appears,
runner bails with status=rate_limited rather than letting the CLI burn the
budget silently.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from eval.metrics import RunMetrics
from eval.runners._common import (
    count_redundant_tool_calls,
    find_root_cause_round,
    run_fix_command,
    write_claude_mcp_config,
)
from eval.runners.base import Case, Runner, RunResult


class ClaudeCodeRunner(Runner):
    name = "claude_code"

    def run(self, case: Case, polaris_enabled: bool, seed: int) -> RunResult:
        if case.workdir:
            cwd = Path(case.workdir)
        else:
            digits = "".join(c for c in case.case_id.split("_")[1] if c.isdigit())
            cwd = Path(f"/tmp/_polaris_case{int(digits):02d}")
        cwd.mkdir(parents=True, exist_ok=True)
        mcp_cfg = write_claude_mcp_config(polaris_enabled)

        cmd = [
            "claude", "-p", case.initial_prompt,
            "--output-format", "stream-json",
            "--verbose",
            "--strict-mcp-config",
            "--mcp-config", str(mcp_cfg),
            "--add-dir", str(cwd),
            "--dangerously-skip-permissions",
        ]
        model = os.environ.get("POLARIS_CLAUDE_MODEL")
        if model:
            cmd += ["--model", model]
        budget = os.environ.get("POLARIS_CLAUDE_MAX_BUDGET_USD")
        if budget:
            cmd += ["--max-budget-usd", budget]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=case.max_rounds * 90,
                cwd=str(cwd),
            )
        except subprocess.TimeoutExpired as e:
            metrics = RunMetrics(None, 0, 0, 0, False, 0)
            return RunResult(
                runner_name=self.name, case_id=case.case_id,
                polaris_enabled=polaris_enabled, metrics=metrics,
                transcript=f"[claude timeout] {e}", seed=seed,
            )

        assistant_texts: list[str] = []
        tool_call_sigs: list[tuple[str, str]] = []
        input_tokens = 0
        output_tokens = 0
        tool_calls = 0
        rate_limited = False
        num_turns = 0

        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            et = ev.get("type", "")
            if et == "rate_limit_event":
                info = ev.get("rate_limit_info", {}) or {}
                if info.get("status", "").startswith("blocked"):
                    rate_limited = True
            if et == "assistant":
                msg = ev.get("message", {}) or {}
                for block in msg.get("content", []) or []:
                    if block.get("type") == "text":
                        assistant_texts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_calls += 1
                        tool_call_sigs.append((
                            block.get("name", ""),
                            json.dumps(block.get("input", {}), sort_keys=True),
                        ))
                usage = msg.get("usage", {}) or {}
                input_tokens += int(usage.get("input_tokens", 0) or 0)
                output_tokens += int(usage.get("output_tokens", 0) or 0)
            if et == "result":
                num_turns = int(ev.get("num_turns", 0) or 0)

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
            ci_pass=False if rate_limited else ci_pass,
            human_intervention_count=0,
        )
        transcript = "\n---\n".join([
            f"[claude exit={proc.returncode} rate_limited={rate_limited} num_turns={num_turns}]",
            proc.stdout or "",
            f"[stderr]\n{proc.stderr or ''}",
            f"[fix_command_test output]\n{fix_out}",
        ])
        try:
            mcp_cfg.unlink()
        except OSError:
            pass
        return RunResult(
            runner_name=self.name, case_id=case.case_id,
            polaris_enabled=polaris_enabled, metrics=metrics,
            transcript=transcript, seed=seed,
            blocked_reason="blocked_agent_rate_limited" if rate_limited else None,
            status="blocked_agent_rate_limited" if rate_limited else "completed",
        )
