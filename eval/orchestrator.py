# Polaris - pattern-based code review tool
# Copyright (C) 2026 Zihang Zhao
# Licensed under AGPL-3.0-only. See LICENSE for details.

"""Run case × runner × {baseline, with_polaris} matrix — hermetic variant.

Per-variant workdir is rebuilt from `eval/fixtures/<case_id>/files/` into
`/tmp/_polaris_runs/<run_id>/<runner>/<case_id>/<variant>/`. The case's
`expected_failure_command` (from the fixture manifest) is executed BEFORE the
agent is invoked; if its stderr doesn't match `expected_failure_stderr_regex`,
the run is tagged `blocked_precondition_failed` and the agent is not called.

Usage:
  python3 -m eval.orchestrator --runner mock --seed 42
  python3 -m eval.orchestrator --runner codex,claude_code,cursor --seed 42
  python3 -m eval.orchestrator --runner codex --case case_001_python_pythonpath
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from pathlib import Path

from eval.hermetic import (
    HermeticContext,
    prepare_variant_workdir,
    scan_contamination,
)
from eval.metrics import MetricDelta, RunMetrics
from eval.runners._common import run_fix_command
from eval.runners.base import Case, Runner, RunResult, load_case
from eval.runners.claude_code_runner import ClaudeCodeRunner
from eval.runners.codex_runner import CodexRunner
from eval.runners.cursor_runner import CursorRunner
from eval.runners.mock_runner import MockRunner

REPO = Path(__file__).resolve().parent.parent
CASES_DIR = REPO / "eval" / "cases"
RUNS_DIR = REPO / "eval" / "runs"

RUNNERS: dict[str, type[Runner]] = {
    "mock": MockRunner,
    "codex": CodexRunner,
    "claude_code": ClaudeCodeRunner,
    "cursor": CursorRunner,
}


def load_all_cases(case_filter: set[str] | None = None) -> list[Case]:
    paths = sorted(CASES_DIR.glob("*.json"))
    out = []
    for p in paths:
        c = load_case(p)
        if case_filter and c.case_id not in case_filter:
            continue
        out.append(c)
    return out


LAUNCH_PAIR_PASS_MIN = 0.50
LAUNCH_REAL_CASE_MIN = 0.50
V0_REAL_CASE_MIN = 0.30


def compute_launch_verdict(runner_names, cases, hard_gate_passing, total_pairs) -> dict:
    reasons: list[str] = []
    if "mock" in runner_names and len(runner_names) == 1:
        return {
            "status": "blocked_mock_only",
            "reasons": ["only MockRunner executed; mock metrics are fabricated and cannot support any external claim"],
            "pair_pass_rate": None,
            "real_case_share": None,
        }
    real_share = (
        sum(1 for c in cases if c.source == "real_issue") / max(1, len(cases))
    )
    real_case_ok = real_share >= LAUNCH_REAL_CASE_MIN
    if not real_case_ok and real_share < V0_REAL_CASE_MIN:
        reasons.append(f"real_issue case share {real_share:.0%} < v0 minimum {V0_REAL_CASE_MIN:.0%}")
    elif not real_case_ok:
        reasons.append(f"real_issue case share {real_share:.0%} < launch minimum {LAUNCH_REAL_CASE_MIN:.0%}")
    pair_rate = hard_gate_passing / max(1, total_pairs) if total_pairs else 0.0
    if pair_rate < LAUNCH_PAIR_PASS_MIN:
        reasons.append(f"hard-gate pair pass rate {pair_rate:.0%} < launch minimum {LAUNCH_PAIR_PASS_MIN:.0%}")
    if total_pairs == 0:
        reasons.append("no real-agent pairs completed; stub runners only")
    status = "pass" if not reasons else "fail"
    return {
        "status": status,
        "reasons": reasons,
        "pair_pass_rate": pair_rate,
        "real_case_share": real_share,
    }


def _blocked_result(
    runner_name: str, case: Case, polaris_enabled: bool, seed: int,
    ctx: HermeticContext,
) -> RunResult:
    metrics = RunMetrics(None, 0, 0, 0, False, 0)
    transcript = "\n---\n".join([
        f"[blocked reason={ctx.blocked_reason}]",
        f"[pre_failure_command]\n{ctx.pre_failure_command}",
        f"[pre_failure_output]\n{ctx.pre_failure_output}",
        f"[expected_stderr_regex]\n{ctx.expected_failure_stderr_regex}",
    ])
    return RunResult(
        runner_name=runner_name,
        case_id=case.case_id,
        polaris_enabled=polaris_enabled,
        metrics=metrics,
        transcript=transcript,
        seed=seed,
        workdir=str(ctx.workdir),
        workdir_manifest_hash=ctx.workdir_manifest_hash,
        pre_failure_reproduced=False,
        pre_failure_command=ctx.pre_failure_command,
        pre_failure_output=ctx.pre_failure_output,
        post_fix_command="",
        post_fix_output="",
        blocked_reason=ctx.blocked_reason,
        contamination_hits=[],
        status=ctx.blocked_reason or "blocked_precondition_failed",
    )


def _adjust_case_for_variant(case: Case, ctx: HermeticContext) -> Case:
    new_sc = dict(case.success_criteria or {})
    new_sc["fix_command_test"] = ctx.fix_command_test_substituted
    return dataclasses.replace(
        case,
        initial_prompt=ctx.initial_prompt_substituted,
        success_criteria=new_sc,
        workdir=str(ctx.workdir),
    )


def orchestrate(
    runner_names: list[str], seed: int, case_filter: set[str] | None = None,
) -> Path:
    cases = load_all_cases(case_filter)
    runners = [RUNNERS[n]() for n in runner_names]
    ts = time.strftime("%Y%m%dT%H%M%S")
    out_dir = RUNS_DIR / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    transcripts_dir = out_dir / "transcripts"
    transcripts_dir.mkdir(exist_ok=True)

    results: list[dict] = []
    deltas: list[dict] = []
    blocked_count = {"blocked_no_fixture": 0, "blocked_precondition_failed": 0,
                     "blocked_precondition_timeout": 0, "blocked_contaminated_run": 0,
                     "blocked_no_expected_failure": 0,
                     "blocked_cursor_transcript_missing": 0,
                     "blocked_agent_rate_limited": 0}

    skip_baseline = bool(os.environ.get("POLARIS_SKIP_BASELINE"))
    variants = (True,) if skip_baseline else (False, True)
    for runner in runners:
        for case in cases:
            pair: dict[bool, RunResult] = {}
            for polaris_enabled in variants:
                variant = "polaris" if polaris_enabled else "baseline"
                raw_case_dict = {
                    "initial_prompt": case.initial_prompt,
                    "success_criteria": case.success_criteria,
                }
                ctx = prepare_variant_workdir(
                    run_id=ts,
                    runner_name=runner.name,
                    case_id=case.case_id,
                    variant=variant,
                    case=raw_case_dict,
                )
                if ctx.blocked_reason:
                    blocked_count[ctx.blocked_reason] = (
                        blocked_count.get(ctx.blocked_reason, 0) + 1
                    )
                    rr = _blocked_result(runner.name, case, polaris_enabled, seed, ctx)
                    pair[polaris_enabled] = rr
                    results.append(rr.to_dict())
                    continue

                adjusted = _adjust_case_for_variant(case, ctx)
                try:
                    rr = runner.run(adjusted, polaris_enabled, seed)
                except NotImplementedError as e:
                    results.append({
                        "runner": runner.name,
                        "case_id": case.case_id,
                        "polaris_enabled": polaris_enabled,
                        "error": str(e),
                    })
                    continue

                post_pass, post_out = run_fix_command(
                    ctx.fix_command_test_substituted
                )
                rr.metrics = dataclasses.replace(rr.metrics, ci_pass=post_pass)
                rr.workdir = str(ctx.workdir)
                rr.workdir_manifest_hash = ctx.workdir_manifest_hash
                rr.pre_failure_reproduced = True
                rr.pre_failure_command = ctx.pre_failure_command
                rr.pre_failure_output = ctx.pre_failure_output[-4000:]
                rr.post_fix_command = ctx.fix_command_test_substituted
                rr.post_fix_output = post_out[-4000:]
                if rr.blocked_reason:
                    blocked_count[rr.blocked_reason] = (
                        blocked_count.get(rr.blocked_reason, 0) + 1
                    )
                hits = scan_contamination(rr.transcript)
                rr.contamination_hits = hits
                if hits:
                    rr.blocked_reason = "blocked_contaminated_run"
                    blocked_count["blocked_contaminated_run"] += 1
                    rr.metrics = dataclasses.replace(rr.metrics, ci_pass=False)

                tpath = transcripts_dir / f"{runner.name}__{case.case_id}__{variant}.txt"
                wrapped = (
                    f"[pre_failure_command]\n{ctx.pre_failure_command}\n"
                    f"[pre_failure_output]\n{ctx.pre_failure_output}\n"
                    f"[pre_failure_reproduced]\ntrue\n"
                    f"[agent_transcript]\n{rr.transcript}\n"
                    f"[post_fix_command]\n{ctx.fix_command_test_substituted}\n"
                    f"[post_fix_output]\n{post_out}\n"
                    f"[post_fix_ci_pass]\n{post_pass}\n"
                    f"[contamination_hits]\n{json.dumps(hits)}\n"
                )
                tpath.write_text(wrapped)
                rr.transcript = wrapped

                pair[polaris_enabled] = rr
                results.append(rr.to_dict())

            if False in pair and True in pair and not (
                pair[False].blocked_reason or pair[True].blocked_reason
            ):
                delta = MetricDelta(
                    baseline=pair[False].metrics,
                    with_polaris=pair[True].metrics,
                )
                deltas.append({
                    "runner": runner.name,
                    "case_id": case.case_id,
                    "summary": delta.summary(),
                })

    hard_gate_passing = sum(1 for d in deltas if d["summary"]["passes_hard_gate"])
    launch_verdict = compute_launch_verdict(
        runner_names=runner_names,
        cases=cases,
        hard_gate_passing=hard_gate_passing,
        total_pairs=len(deltas),
    )
    summary = {
        "runners": runner_names,
        "seed": seed,
        "cases_total": len(cases),
        "runs_attempted": len(runners) * len(cases) * 2,
        "runs_completed": sum(1 for r in results if "error" not in r and not r.get("blocked_reason")),
        "runs_blocked": blocked_count,
        "deltas": deltas,
        "hard_gate_passing_pairs": hard_gate_passing,
        "hard_gate_total_pairs": len(deltas),
        "launch_verdict": launch_verdict,
        "narrative_compliance": (
            "Per NARRATIVE.md §4: token-only gains do NOT count. "
            "A runner/case pair passes only if CI pass improves OR "
            "rounds_to_root_cause drops >= 30%."
        ),
        "hermetic_contract": (
            "Every (runner, case, variant) executes in a fresh workdir under "
            "/tmp/_polaris_runs/<run_id>/... The fixture's "
            "expected_failure_command runs before the agent; if its stderr "
            "does not match expected_failure_stderr_regex, the run is blocked "
            "and the agent is NOT invoked. Evidence-eligible runs must also "
            "have no contamination phrases in the transcript."
        ),
    }
    (out_dir / "results.json").write_text(json.dumps(results, indent=2))
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return out_dir


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runner", default="mock",
                    help="comma-separated: mock,codex,claude_code,cursor")
    ap.add_argument("--seed", type=int, default=20260419)
    ap.add_argument("--case", default=None,
                    help="comma-separated case_id list (default: all)")
    args = ap.parse_args()
    names = [n.strip() for n in args.runner.split(",")]
    for n in names:
        if n not in RUNNERS:
            print(f"unknown runner: {n}", file=sys.stderr)
            return 2
    case_filter = set(c.strip() for c in args.case.split(",")) if args.case else None
    orchestrate(names, args.seed, case_filter)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
