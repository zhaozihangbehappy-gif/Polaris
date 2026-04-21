"""Unified runner contract — 木桶 equal across all three ends.

Every end-runner (codex, claude_code, cursor) implements the same .run()
signature. Orchestrator stays agent-agnostic; adding a fourth runner later
(e.g. Gemini CLI) only requires implementing Runner, not changing orchestration.
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional

from eval.metrics import RunMetrics


@dataclass
class Case:
    case_id: str
    source: str
    ecosystem: str
    initial_prompt: str
    success_criteria: dict
    max_rounds: int
    reverse_from_pattern: Optional[str] = None
    repo_snapshot_path: Optional[str] = None
    workdir: Optional[str] = None
    pattern_id: Optional[str] = None
    source_pool: Optional[str] = None
    fixture_strategy: Optional[str] = None
    promotion_eligible: Optional[bool] = None
    error_class: Optional[str] = None


@dataclass
class RunResult:
    runner_name: str
    case_id: str
    polaris_enabled: bool
    metrics: RunMetrics
    transcript: str
    seed: int
    workdir: Optional[str] = None
    workdir_manifest_hash: str = ""
    pre_failure_reproduced: bool = False
    pre_failure_command: str = ""
    pre_failure_output: str = ""
    post_fix_command: str = ""
    post_fix_output: str = ""
    blocked_reason: Optional[str] = None
    contamination_hits: list = None
    status: str = "completed"

    @property
    def transcript_hash(self) -> str:
        return hashlib.sha256(self.transcript.encode()).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["metrics"] = self.metrics.to_dict()
        d["transcript_hash"] = self.transcript_hash
        if d.get("contamination_hits") is None:
            d["contamination_hits"] = []
        return d


class Runner(ABC):
    name: str = "abstract"

    @abstractmethod
    def run(self, case: Case, polaris_enabled: bool, seed: int) -> RunResult:
        """Execute one case. Must be deterministic given (case, polaris_enabled, seed)."""
        raise NotImplementedError


def load_case(path) -> Case:
    data = json.loads(open(path).read())
    known = {f for f in Case.__dataclass_fields__}
    filtered = {k: v for k, v in data.items() if k in known}
    return Case(**filtered)
