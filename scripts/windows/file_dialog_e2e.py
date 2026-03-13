#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path('/home/administrator/.openclaw/workspace')
RUN_DIR = WORKSPACE / 'artifacts' / 'gui-template-runs'
RUN_DIR.mkdir(parents=True, exist_ok=True)


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')


def ps_file(path: Path) -> str:
    return subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip()


def run_ps_file(path: Path) -> str:
    cmd = ['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps_file(path)]
    return subprocess.check_output(cmd, text=True).strip()


def detect_dialog() -> list[dict]:
    out = run_ps_file(WORKSPACE / 'scripts/windows/detect_open_file_dialog.ps1')
    if not out:
        return []
    return json.loads(out)


def main() -> int:
    run_id = stamp()
    result_path = RUN_DIR / f'file_dialog_select_file-{run_id}.json'
    result = {'run_id': run_id, 'template': 'file_dialog_select_file', 'started_at_utc': datetime.now(timezone.utc).isoformat(), 'status': 'running'}
    try:
        run_ps_file(WORKSPACE / 'scripts/windows/start_open_file_dialog_host.ps1')
        deadline = time.time() + 15
        dialogs = []
        while time.time() < deadline:
            dialogs = detect_dialog()
            if dialogs:
                break
            time.sleep(0.4)
        if not dialogs:
            raise RuntimeError('Open file dialog did not appear')
        result['dialog_detect'] = dialogs
        cmd = [
            'python3',
            str(WORKSPACE / 'scripts/windows/gui_template_orchestrator.py'),
            'file_dialog_select_file',
            'cabinet-12cell-concept.blend',
        ]
        out = subprocess.check_output(cmd, text=True, env={**dict(), **{'OPENCLAW_DESKTOP_KEY': 'desktop-secret'}})
        result['orchestrator_stdout'] = out.strip()
        latest = sorted(RUN_DIR.glob('file_dialog_select_file-*.json'))[-1]
        result['orchestrator_result_path'] = str(latest)
        result['orchestrator_result'] = json.loads(latest.read_text(encoding='utf-8'))
        result['status'] = result['orchestrator_result'].get('status', 'unknown')
    except Exception as exc:  # noqa: BLE001
        result['status'] = 'fail'
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        result['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(str(result_path))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
