#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKSPACE = Path('/home/administrator/.openclaw/workspace')
RUN_DIR = WORKSPACE / 'artifacts' / 'gui-state-runs'
RUN_DIR.mkdir(parents=True, exist_ok=True)


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')


def run_template(args: list[str], env: dict[str, str] | None = None) -> dict[str, Any]:
    cmd = ['python3', str(WORKSPACE / 'scripts/windows/gui_template_orchestrator.py'), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180)
    out = (proc.stdout or '').strip().splitlines()
    result_path = Path(out[-1]) if out else None
    result = {
        'returncode': proc.returncode,
        'stdout': proc.stdout,
        'stderr': proc.stderr,
    }
    if result_path and result_path.exists():
        result['result_path'] = str(result_path)
        result['result'] = json.loads(result_path.read_text(encoding='utf-8'))
    return result


@dataclass
class StateStep:
    name: str
    status: str
    detail: str
    payload: dict[str, Any]


def main() -> int:
    scenario = sys.argv[1] if len(sys.argv) > 1 else 'delivery_open_and_focus'
    run_id = stamp()
    out_path = RUN_DIR / f'{scenario}-{run_id}.json'
    record: dict[str, Any] = {
        'run_id': run_id,
        'scenario': scenario,
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'running',
        'steps': [],
    }
    env = dict(**subprocess.os.environ)
    env.setdefault('OPENCLAW_DESKTOP_KEY', 'desktop-secret')
    try:
        if scenario == 'delivery_open_and_focus':
            r1 = run_template([
                'explorer_open_file',
                'D:\\Administrator\\Documents\\Playground\\openclaw-upstream\\artifacts\\delivery',
                'cabinet-12cell-concept.blend',
            ], env)
            s1 = 'pass' if r1.get('returncode') == 0 and r1.get('result', {}).get('status') == 'pass' else 'fail'
            record['steps'].append(asdict(StateStep('explorer_open_file', s1, 'open file from Explorer via calibrated template', r1)))
            if s1 != 'pass':
                raise RuntimeError('explorer_open_file failed')

            r2 = run_template(['blender_focus'], env)
            s2 = 'pass' if r2.get('returncode') == 0 and r2.get('result', {}).get('status') == 'pass' else 'fail'
            record['steps'].append(asdict(StateStep('blender_focus', s2, 'focus Blender via calibrated template', r2)))
            if s2 != 'pass':
                raise RuntimeError('blender_focus failed')

            record['status'] = 'pass'
        else:
            raise RuntimeError(f'unknown scenario: {scenario}')
    except Exception as exc:  # noqa: BLE001
        record['status'] = 'fail'
        record['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        record['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        print(str(out_path))
    return 0 if record['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
