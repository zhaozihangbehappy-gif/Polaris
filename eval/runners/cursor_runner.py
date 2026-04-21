"""Cursor runner — manual-transcript ingest (v1).

Cursor's headless automation is not stable across versions. For v1, the user
runs Cursor interactively on the case and hand-exports a transcript to:

  eval/runs/manual_cursor/<case_id>__<variant>.json

where <variant> is "baseline" or "polaris". Expected shape:

  {
    "turns": [
      {"role": "user"|"assistant", "text": "...", "tool_calls": [{"name","input"}]?},
      ...
    ],
    "usage": {"input_tokens": int, "output_tokens": int}?,
    "ci_pass_override": bool?    // optional; if omitted we run fix_command_test
  }

If the transcript file is missing, runner reports status=missing — does NOT
synthesize metrics. 木桶 stays honest about the manual gap.
"""
from __future__ import annotations

import json
from pathlib import Path

from eval.metrics import RunMetrics
from eval.runners._common import (
    count_redundant_tool_calls,
    find_root_cause_round,
    run_fix_command,
)
from eval.runners.base import Case, Runner, RunResult

REPO = Path(__file__).resolve().parent.parent.parent
MANUAL_DIR = REPO / "eval" / "runs" / "manual_cursor"


class CursorRunner(Runner):
    name = "cursor"

    def _transcript_path(self, case_id: str, polaris_enabled: bool) -> Path:
        variant = "polaris" if polaris_enabled else "baseline"
        return MANUAL_DIR / f"{case_id}__{variant}.json"

    def run(self, case: Case, polaris_enabled: bool, seed: int) -> RunResult:
        path = self._transcript_path(case.case_id, polaris_enabled)
        if not path.exists():
            metrics = RunMetrics(None, 0, 0, 0, False, 0)
            return RunResult(
                runner_name=self.name, case_id=case.case_id,
                polaris_enabled=polaris_enabled, metrics=metrics,
                transcript=f"[cursor manual transcript missing: {path}]",
                seed=seed,
                blocked_reason="blocked_cursor_transcript_missing",
                status="blocked_cursor_transcript_missing",
            )

        data = json.loads(path.read_text())
        assistant_texts: list[str] = []
        tool_call_sigs: list[tuple[str, str]] = []
        for turn in data.get("turns", []):
            if turn.get("role") == "assistant":
                assistant_texts.append(turn.get("text", ""))
                for tc in turn.get("tool_calls", []) or []:
                    tool_call_sigs.append((
                        tc.get("name", ""),
                        json.dumps(tc.get("input", {}), sort_keys=True),
                    ))

        usage = data.get("usage", {}) or {}
        ci_pass_override = data.get("ci_pass_override")
        if ci_pass_override is None:
            ci_pass, fix_out = run_fix_command(case.success_criteria["fix_command_test"])
        else:
            ci_pass = bool(ci_pass_override)
            fix_out = "[ci_pass_override used; fix_command_test not re-run]"

        root_round = find_root_cause_round(
            assistant_texts, case.success_criteria.get("root_cause_regex", "")
        )
        redundant = count_redundant_tool_calls(tool_call_sigs)

        metrics = RunMetrics(
            rounds_to_root_cause=root_round,
            redundant_actions_count=redundant,
            token_consumption=int(usage.get("input_tokens", 0) or 0)
                + int(usage.get("output_tokens", 0) or 0),
            tool_calls=len(tool_call_sigs),
            ci_pass=ci_pass,
            human_intervention_count=0,
        )
        transcript = "\n---\n".join([
            f"[cursor manual transcript {path}]",
            json.dumps(data, indent=2),
            f"[fix_command_test output]\n{fix_out}",
        ])
        return RunResult(
            runner_name=self.name, case_id=case.case_id,
            polaris_enabled=polaris_enabled, metrics=metrics,
            transcript=transcript, seed=seed,
        )
