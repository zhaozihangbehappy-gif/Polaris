# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Mock runner — deterministic synthetic metrics for plumbing validation.

PURPOSE: prove the orchestrator, metrics comparison, and reporting pipeline
end-to-end without requiring real agent access. MUST NEVER be used for any
external claim about Polaris performance. Its numbers are fabricated.
"""
from __future__ import annotations

import hashlib
import random

from eval.metrics import RunMetrics
from eval.runners.base import Case, Runner, RunResult


class MockRunner(Runner):
    name = "mock"

    def run(self, case: Case, polaris_enabled: bool, seed: int) -> RunResult:
        rng = random.Random(f"{seed}:{case.case_id}:{polaris_enabled}")
        base_rounds = rng.randint(5, 12)
        base_tokens = rng.randint(3000, 8000)
        base_tool_calls = rng.randint(8, 20)

        if polaris_enabled:
            rounds = max(1, base_rounds - rng.randint(2, 5))
            tokens = base_tokens - rng.randint(500, 1500) + 280  # +polaris context
            tool_calls = base_tool_calls - rng.randint(2, 6)
            ci_pass = rng.random() > 0.2
            redundant = rng.randint(0, 2)
        else:
            rounds = base_rounds
            tokens = base_tokens
            tool_calls = base_tool_calls
            ci_pass = rng.random() > 0.55
            redundant = rng.randint(2, 6)

        metrics = RunMetrics(
            rounds_to_root_cause=rounds,
            redundant_actions_count=redundant,
            token_consumption=tokens,
            tool_calls=tool_calls,
            ci_pass=ci_pass,
            human_intervention_count=0,
        )
        transcript = (
            f"[MOCK transcript for {case.case_id} polaris={polaris_enabled} "
            f"seed={seed}]\n"
            f"rounds={rounds} tokens={tokens} tool_calls={tool_calls} "
            f"ci_pass={ci_pass}\n"
        )
        return RunResult(
            runner_name=self.name,
            case_id=case.case_id,
            polaris_enabled=polaris_enabled,
            metrics=metrics,
            transcript=transcript,
            seed=seed,
        )
