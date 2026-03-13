#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, '/home/administrator/.openclaw/workspace/scripts/gui')
from bridge_client import BridgeClient  # type: ignore

WORKSPACE = Path('/home/administrator/.openclaw/workspace')
CAL_DIR = Path('/mnt/d/Administrator/Documents/Playground/openclaw-upstream/artifacts/gui-template-calibration')
RUN_DIR = WORKSPACE / 'artifacts' / 'gui-template-runs'
RUN_DIR.mkdir(parents=True, exist_ok=True)


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')


def newest_calibration(kind: str, start_ts: float) -> Path:
    deadline = time.time() + 20
    pattern = f'{kind}-*.json'
    while time.time() < deadline:
        candidates = [p for p in CAL_DIR.glob(pattern) if p.stat().st_mtime >= start_ts - 1]
        if candidates:
            return max(candidates, key=lambda p: p.stat().st_mtime)
        time.sleep(0.4)
    raise TimeoutError(f'No calibration file appeared for {kind}')


def run_calibration(kind: str, *args: str) -> dict:
    script = WORKSPACE / 'scripts/windows/gui_template_builder.py'
    winpath = subprocess.check_output(['wslpath', '-w', str(script)], text=True).strip()
    ps_args = ' '.join([f'"{a}"' for a in (kind, *args)])
    cmd = ['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe', '-NoProfile', '-Command', f'py "{winpath}" {ps_args}']
    start_ts = time.time()
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    cal_path = newest_calibration(kind, start_ts)
    data = json.loads(cal_path.read_text(encoding='utf-8'))
    if data.get('status') != 'pass':
        raise RuntimeError(data.get('error', f'Calibration failed for {kind}'))
    return data['payload']


def write_plan(name: str, payload: dict) -> Path:
    plan_dir = WORKSPACE / 'artifacts/gui-macros'
    plan_dir.mkdir(parents=True, exist_ok=True)
    path = plan_dir / f'{name}.json'
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def smooth_points(*coords):
    return [{'x': x, 'y': y, 'steps': 8, 'delayMs': 12} for x, y in coords]


def build_explorer_open_file(path_str: str, file_name: str) -> dict:
    d = run_calibration('explorer_open_file', path_str, file_name)
    wr = d['window_rect']
    sr = d.get('search_rect') or {'center_x': wr['right'] - 180, 'center_y': wr['top'] + 48}
    ir = d.get('item_rect') or {'center_x': wr['left'] + 360, 'center_y': wr['top'] + 210}
    return {
        'template': 'explorer_open_file',
        'calibration': d,
        'steps': [
            {'kind': 'activateExplorerPath', 'path': path_str, 'waitMs': 1400},
            {'kind': 'movePath', 'points': smooth_points((wr['left'] + 180, wr['top'] + 90), (wr['left'] + wr['width']//2, wr['top'] + 76), (sr['center_x'], sr['center_y']))},
            {'kind': 'click'},
            {'kind': 'sendKeys', 'text': file_name, 'preDelayMs': 100},
            {'kind': 'wait', 'ms': 120},
            {'kind': 'sendKeys', 'text': '{ENTER}', 'preDelayMs': 30},
            {'kind': 'wait', 'ms': 1500},
            {'kind': 'movePath', 'points': smooth_points((wr['left'] + wr['width'] - 260, wr['top'] + 140), (wr['left'] + wr['width']//2, wr['top'] + 190), (ir['center_x'], ir['center_y']))},
            {'kind': 'doubleClick', 'intervalMs': 110},
            {'kind': 'wait', 'ms': 1000}
        ]
    }


def build_explorer_select_file(path_str: str, file_name: str) -> dict:
    payload = build_explorer_open_file(path_str, file_name)
    payload['template'] = 'explorer_select_file'
    payload['steps'][-2] = {'kind': 'click'}
    return payload


def build_blender_focus() -> dict:
    d = run_calibration('blender_focus')
    wr = d['window_rect']
    return {
        'template': 'blender_focus',
        'calibration': d,
        'steps': [
            {'kind': 'movePath', 'points': smooth_points((wr['left'] + 120, wr['top'] + 90), (wr['left'] + wr['width']//2, wr['top'] + 70), (wr['left'] + wr['width']//2, wr['top'] + 120))},
            {'kind': 'click'},
            {'kind': 'wait', 'ms': 250}
        ]
    }


def build_file_dialog_select_file(file_name: str) -> dict:
    d = run_calibration('file_dialog_select_file', file_name)
    wr = d['window_rect']
    er = d.get('filename_edit_rect') or {'center_x': wr['left'] + wr['width']//2, 'center_y': wr['bottom'] - 60}
    br = d.get('confirm_button_rect') or {'center_x': wr['right'] - 90, 'center_y': wr['bottom'] - 36}
    return {
        'template': 'file_dialog_select_file',
        'calibration': d,
        'steps': [
            {'kind': 'movePath', 'points': smooth_points((wr['left'] + 120, wr['top'] + 90), (er['center_x'], er['center_y']))},
            {'kind': 'click'},
            {'kind': 'sendKeys', 'text': file_name, 'preDelayMs': 100},
            {'kind': 'wait', 'ms': 100},
            {'kind': 'movePath', 'points': smooth_points((br['center_x'] - 120, br['center_y'] - 20), (br['center_x'], br['center_y']))},
            {'kind': 'click'},
            {'kind': 'wait', 'ms': 350}
        ]
    }


def verify_blender_window() -> list[dict]:
    client = BridgeClient.from_env()
    data = client.list_windows()
    wins = (data.get('data') or {}).get('windows') or []
    return [w for w in wins if 'cabinet-12cell-concept' in str(w.get('title','')).lower() or ('blender' in str(w.get('title','')).lower() and str(w.get('class_name','')) == 'GHOST_WindowClass')]


def main() -> int:
    kind = sys.argv[1]
    run_id = stamp()
    result_path = RUN_DIR / f'{kind}-{run_id}.json'
    result = {
        'run_id': run_id,
        'template': kind,
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'running'
    }
    try:
        if kind == 'explorer_open_file':
            payload = build_explorer_open_file(sys.argv[2], sys.argv[3])
        elif kind == 'explorer_select_file':
            payload = build_explorer_select_file(sys.argv[2], sys.argv[3])
        elif kind == 'blender_focus':
            payload = build_blender_focus()
        elif kind == 'file_dialog_select_file':
            payload = build_file_dialog_select_file(sys.argv[2])
        else:
            raise SystemExit(f'unknown template kind: {kind}')

        plan_name = f'{kind}-{run_id}'
        plan_path = write_plan(plan_name, payload)
        subprocess.run([str(WORKSPACE / 'scripts/windows/run-gui-macro-from-wsl.sh'), str(plan_path)], check=True, capture_output=True, text=True)
        result['status'] = 'pass'
        result['plan_path'] = str(plan_path)
        result['calibration'] = payload.get('calibration')
        if kind in ('explorer_open_file', 'blender_focus'):
            try:
                result['bridge_verify'] = verify_blender_window()
            except Exception as exc:  # noqa: BLE001
                result['bridge_verify_error'] = f'{type(exc).__name__}: {exc}'
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
