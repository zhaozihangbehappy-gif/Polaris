# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Polaris pattern schema v4.

Adds the five structured-asset fields Codex specified in the 2026-04-19 review,
plus agent_reproducibility — the liveness gate that controls whether a pattern
qualifies for the verified-live release tier.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal, Optional

SCHEMA_VERSION = 4

AgentName = Literal["cursor", "claude_code", "codex"]
ReproStatus = Literal[
    "verified_live",
    "not_reproducible",
    "untested",
    "invalidated_contaminated_fixture",
    "invalidated_synthetic_recipe",
    "blocked_precondition_failed",
    "blocked_contaminated_run",
    "authored_fixture_candidate",
    "authoring_failed",
]


@dataclass
class TriggerSignals:
    stderr_regex: list[str] = field(default_factory=list)
    file_markers: list[str] = field(default_factory=list)
    package_managers: list[str] = field(default_factory=list)
    ci_env: list[str] = field(default_factory=list)


@dataclass
class FalsePath:
    wrong_guess: str
    why_agents_try_it: str


@dataclass
class ShortestVerification:
    command: str
    trigger_env: dict[str, str] = field(default_factory=dict)
    expected_stderr_match: Optional[str] = None
    expected_fix_outcome: Optional[str] = None


@dataclass
class FixPath:
    structured_hints: list[dict] = field(default_factory=list)
    fix_command: Optional[str] = None
    fix_env: dict[str, str] = field(default_factory=dict)
    description: str = ""


@dataclass
class ApplicabilityBounds:
    applies_when: list[str] = field(default_factory=list)
    do_not_apply_when: list[str] = field(default_factory=list)


VALID_AGENTS = {"cursor", "claude_code", "codex"}
VALID_STATUSES = {
    "verified_live",
    "not_reproducible",
    "untested",
    "invalidated_contaminated_fixture",
    "invalidated_synthetic_recipe",
    "blocked_precondition_failed",
    "blocked_contaminated_run",
    "authored_fixture_candidate",
    "authoring_failed",
}
COUNTING_STATUS = "verified_live"
INVALIDATED_STATUSES = {
    "invalidated_contaminated_fixture",
    "invalidated_synthetic_recipe",
    "blocked_precondition_failed",
    "blocked_contaminated_run",
}
AUTHORED_STATUSES = {"authored_fixture_candidate"}


@dataclass
class AgentReproEvidence:
    agent: AgentName
    agent_version: str
    date_verified: str
    status: ReproStatus
    artifact_path: str
    transcript_hash: str
    notes: str = ""
    model: str = ""
    pre_failure_reproduced: bool = False
    workdir_manifest_hash: str = ""
    invalidation_reason: str = ""
    invalidated_at: str = ""

    def audit_errors(self) -> list[str]:
        from datetime import datetime
        errs: list[str] = []
        if self.agent not in VALID_AGENTS:
            errs.append(f"agent must be one of {sorted(VALID_AGENTS)}")
        if self.status not in VALID_STATUSES:
            errs.append(f"status must be one of {sorted(VALID_STATUSES)}")
        try:
            datetime.fromisoformat(self.date_verified)
        except ValueError:
            errs.append("date_verified must be ISO-8601")
        if self.status == "verified_live":
            if not self.artifact_path:
                errs.append("verified_live requires artifact_path")
            import re
            if not re.fullmatch(r"[0-9a-f]{64}", self.transcript_hash or ""):
                errs.append("transcript_hash must be sha256 (64 lowercase hex)")
            if not self.pre_failure_reproduced:
                errs.append(
                    "verified_live requires pre_failure_reproduced=true "
                    "(hermetic fixture rebuilt the failure before the agent acted)"
                )
        return errs


@dataclass
class AgentReproducibility:
    evidence: list[AgentReproEvidence] = field(default_factory=list)

    def counts_toward_1000(self, max_age_days: int = 90) -> bool:
        """Legacy internal name: true iff verified_live on >=1 agent within window."""
        from datetime import datetime, timedelta, timezone
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        for ev in self.evidence:
            if ev.status != "verified_live":
                continue
            try:
                d = datetime.fromisoformat(ev.date_verified)
            except ValueError:
                continue
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            if d >= cutoff:
                return True
        return False


@dataclass
class AuthoredFile:
    path: str
    content: str


@dataclass
class AuthoredReviewerRecord:
    validated_in_sandbox_at: str
    sandbox_pre_fix_exit_code: int
    sandbox_pre_fix_stderr_match: bool
    sandbox_post_fix_exit_code: int
    sandbox_workdir_hash_pre: str
    sandbox_workdir_hash_post: str
    notes: str = ""


@dataclass
class AuthoredFixture:
    authored_at: str
    authored_by: AgentName
    authored_with_prompt_sha256: str
    verification_command: str
    expected_stderr_regex: str
    files: list[AuthoredFile] = field(default_factory=list)
    reference_fix_files: list[AuthoredFile] = field(default_factory=list)
    reviewer_record: Optional[AuthoredReviewerRecord] = None

    def is_sandbox_valid(self) -> bool:
        """Reviewer contract: pre-fix must fail and match regex; post-fix must pass."""
        rr = self.reviewer_record
        if rr is None:
            return False
        return (
            rr.sandbox_pre_fix_exit_code != 0
            and rr.sandbox_pre_fix_stderr_match
            and rr.sandbox_post_fix_exit_code == 0
        )


@dataclass
class PatternV4:
    pattern_id: str
    ecosystem: str
    error_class: str
    description: str
    source: str
    trigger_signals: TriggerSignals
    false_paths: list[FalsePath]
    shortest_verification: ShortestVerification
    fix_path: FixPath
    applicability_bounds: ApplicabilityBounds
    agent_reproducibility: AgentReproducibility
    legacy_v3: Optional[dict] = None
    needs_human_review: list[str] = field(default_factory=list)
    authored_fixture: Optional[AuthoredFixture] = None

    def to_dict(self) -> dict:
        return asdict(self)


REQUIRED_TOP_FIELDS = [
    "pattern_id", "ecosystem", "error_class", "description", "source",
    "trigger_signals", "false_paths", "shortest_verification",
    "fix_path", "applicability_bounds", "agent_reproducibility",
]


def _is_synthetic_recipe(cmd: str) -> bool:
    """Detect contamination-by-construction recipes: any shell wrapper whose
    *effective* body is just `echo "<static>"; exit <const>` with no real tool
    invocation in between. Strips `bash -c '...'` / `sh -c "..."` and removes
    echo-string + exit-const pairs, then checks what remains.

    These recipes cannot distinguish a real fix from agent inaction: the exit
    code is constant regardless of agent work, so the hermetic harness's pre/
    post gates are vacuous. Any such recipe blocks promotion to verified_live."""
    import re
    if not cmd:
        return False
    s = cmd.strip()
    # Unwrap bash -c '...' or sh -c "..."
    m = re.match(r"^(?:bash|sh)\s+-c\s+(['\"])(?P<body>.*)\1\s*$", s, re.DOTALL)
    body = m.group("body") if m else s
    # Remove one or more chained `echo "..."` or `echo '...'` (with optional `>&2`)
    body = re.sub(r"echo\s+\"[^\"]*\"\s*(>&2)?\s*;?\s*", "", body)
    body = re.sub(r"echo\s+'[^']*'\s*(>&2)?\s*;?\s*", "", body)
    # Remove trailing `exit <N>`
    body = re.sub(r"exit\s+\d+\s*;?\s*", "", body)
    # Remove stray separators/whitespace
    body = re.sub(r"[\s;&|]+", "", body)
    return body == ""


def pattern_level_audit_errors(raw: dict) -> list[str]:
    """Pattern-level audit on top of per-evidence audit_errors().

    Contract: any verified_live evidence row requires the pattern to carry a
    sandbox-valid `authored_fixture`. The synthetic shortest_verification /
    fix_path recipes (echo-only, `|| true`, or self-creating state) cannot
    distinguish a real fix from agent inaction, so they are never sufficient
    evidence on their own. Patterns that currently ship only those recipes
    must first be authored and sandbox-validated before verified_live counts.
    """
    errs: list[str] = []
    af = raw.get("authored_fixture")
    for ev in (raw.get("agent_reproducibility") or {}).get("evidence", []) or []:
        if (ev.get("status") or "") != "verified_live":
            continue
        if not af:
            errs.append(
                "verified_live requires a pattern-level authored_fixture "
                "(real files + real verification_command + sandbox-validated "
                "pre-fix-fails / post-fix-passes)"
            )
            continue
        rr = af.get("reviewer_record") or {}
        if not (
            rr.get("sandbox_pre_fix_exit_code") not in (None, 0)
            and rr.get("sandbox_pre_fix_stderr_match")
            and rr.get("sandbox_post_fix_exit_code") == 0
        ):
            errs.append(
                "verified_live row references an authored_fixture that is "
                "not sandbox-valid (pre must fail+match, post must pass)"
            )
    return errs


def validate_shape(raw: dict) -> list[str]:
    """Return list of shape errors; empty list == valid."""
    errors: list[str] = []
    for f in REQUIRED_TOP_FIELDS:
        if f not in raw:
            errors.append(f"missing field: {f}")
    if "trigger_signals" in raw and not isinstance(raw["trigger_signals"], dict):
        errors.append("trigger_signals must be dict")
    if "false_paths" in raw and not isinstance(raw["false_paths"], list):
        errors.append("false_paths must be list")
    if "agent_reproducibility" in raw:
        ar = raw["agent_reproducibility"]
        if not isinstance(ar, dict) or "evidence" not in ar:
            errors.append("agent_reproducibility must contain 'evidence' list")
    return errors
