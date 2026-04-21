"""Run ONE runner on ONE case, baseline only. No matrix, no verdict.

Usage:
  python3 -m eval.smoke_one codex case_001_python_pythonpath
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from eval.runners.base import Case
from eval.runners.codex_runner import CodexRunner
from eval.runners.claude_code_runner import ClaudeCodeRunner

RUNNERS = {"codex": CodexRunner, "claude_code": ClaudeCodeRunner}


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    runner_name, case_id = sys.argv[1], sys.argv[2]
    case_path = Path(__file__).parent / "cases" / f"{case_id}.json"
    case_data = json.loads(case_path.read_text())
    case = Case(**case_data)
    runner = RUNNERS[runner_name]()
    print(f"[smoke] running {runner_name} on {case_id} (baseline) ...", flush=True)
    result = runner.run(case, polaris_enabled=False, seed=20260419)
    print(f"[metrics] {result.metrics}")
    print(f"[transcript head]\n{result.transcript[:2000]}")


if __name__ == "__main__":
    main()
