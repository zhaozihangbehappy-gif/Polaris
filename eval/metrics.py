"""Codex's five metrics, strictly collected — no "hit rate" smuggling.

A run produces a RunMetrics. Comparison between baseline and with_polaris
produces a MetricDelta. The reporter computes whether the delta passes the
anti-self-hype gate: CI pass rate OR rounds_to_root_cause must improve >=30%.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class RunMetrics:
    rounds_to_root_cause: Optional[int]
    redundant_actions_count: int
    token_consumption: int
    tool_calls: int
    ci_pass: bool
    human_intervention_count: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MetricDelta:
    baseline: RunMetrics
    with_polaris: RunMetrics

    def ci_pass_improved(self) -> bool:
        return (not self.baseline.ci_pass) and self.with_polaris.ci_pass

    def rounds_pct_reduction(self) -> Optional[float]:
        b = self.baseline.rounds_to_root_cause
        p = self.with_polaris.rounds_to_root_cause
        if b is None or p is None or b <= 0:
            return None
        return (b - p) / b * 100

    def passes_hard_gate(self, rounds_threshold_pct: float = 30.0) -> bool:
        """NARRATIVE.md §4 anti-self-hype gate: token-only gains don't count."""
        if self.ci_pass_improved():
            return True
        red = self.rounds_pct_reduction()
        return red is not None and red >= rounds_threshold_pct

    def summary(self) -> dict:
        return {
            "ci_pass_improved": self.ci_pass_improved(),
            "rounds_pct_reduction": self.rounds_pct_reduction(),
            "token_delta": self.with_polaris.token_consumption - self.baseline.token_consumption,
            "tool_calls_delta": self.with_polaris.tool_calls - self.baseline.tool_calls,
            "passes_hard_gate": self.passes_hard_gate(),
        }
