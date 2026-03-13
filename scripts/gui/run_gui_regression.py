#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bridge_client import BridgeClient, BridgeError
from window_ops import set_window_rect


@dataclass
class ScenarioResult:
    scenario_id: str
    status: str
    detail: str
    evidence: dict[str, Any]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def pick_blender_window(windows_payload: Any, title_pattern: str, class_name: str) -> dict[str, Any] | None:
    windows = ((windows_payload or {}).get('data') or {}).get('windows') or []
    needle = title_pattern.replace('*', '').lower()
    for win in windows:
        title = str(win.get('title', ''))
        klass = str(win.get('class_name', ''))
        if needle in title.lower() and klass == class_name:
            return win
    return None


def refresh_window(client: BridgeClient, title_pattern: str, class_name: str) -> dict[str, Any]:
    windows_payload = client.list_windows()
    return pick_blender_window(windows_payload, title_pattern, class_name) or {}


def baseline_step(client: BridgeClient, win: dict[str, Any], purpose_prefix: str) -> dict[str, Any]:
    hwnd = int(win['hwnd'])
    rect = win['rect']
    center_x = int(rect['left'] + rect['width'] / 2)
    center_y = int(rect['top'] + rect['height'] / 2)
    return {
        'hwnd': hwnd,
        'title': win.get('title'),
        'class_name': win.get('class_name'),
        'rect': rect,
        'activation': client.activate(hwnd),
        'capture': client.capture_window(hwnd, f'{purpose_prefix}-capture'),
        'move': client.move_mouse(hwnd, center_x, center_y, f'{purpose_prefix}-center-move'),
    }


def scenario_g1_baseline(client: BridgeClient, win: dict[str, Any], run_dir: Path) -> ScenarioResult:
    evidence = baseline_step(client, win, 'g1-baseline')
    (run_dir / 'g1-baseline.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False))
    return ScenarioResult('G1', 'pass', 'Baseline activation/capture/move succeeded', evidence)


def scenario_g2_moved_window(client: BridgeClient, win: dict[str, Any], run_dir: Path, title_pattern: str, class_name: str) -> ScenarioResult:
    rect = win['rect']
    new_left = 160
    new_top = 120
    move_window = set_window_rect(int(win['hwnd']), new_left, new_top, int(rect['width']), int(rect['height']))
    refreshed = refresh_window(client, title_pattern, class_name)
    if not refreshed:
        raise BridgeError('Blender window not found after moved-window operation')
    evidence = {
        'window_move': move_window,
        'refreshed_window': refreshed,
        'baseline_after_move': baseline_step(client, refreshed, 'g2-moved-window'),
    }
    (run_dir / 'g2-moved-window.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False))
    return ScenarioResult('G2', 'pass', 'Moved-window scenario succeeded', evidence)


def scenario_g3_resized_window(client: BridgeClient, win: dict[str, Any], run_dir: Path, title_pattern: str, class_name: str) -> ScenarioResult:
    rect = win['rect']
    new_width = max(1280, int(rect['width']) - 400)
    new_height = max(900, int(rect['height']) - 250)
    resize_window = set_window_rect(int(win['hwnd']), int(rect['left']), int(rect['top']), new_width, new_height)
    refreshed = refresh_window(client, title_pattern, class_name)
    if not refreshed:
        raise BridgeError('Blender window not found after resized-window operation')
    evidence = {
        'window_resize': resize_window,
        'refreshed_window': refreshed,
        'baseline_after_resize': baseline_step(client, refreshed, 'g3-resized-window'),
    }
    (run_dir / 'g3-resized-window.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False))
    return ScenarioResult('G3', 'pass', 'Resized-window scenario succeeded', evidence)


def scenario_g5_repeated_runs(client: BridgeClient, win: dict[str, Any], run_dir: Path, repeats: int) -> ScenarioResult:
    attempts: list[dict[str, Any]] = []
    for index in range(1, repeats + 1):
        attempt = baseline_step(client, win, f'g5-run-{index}')
        attempt['attempt'] = index
        attempts.append(attempt)
    evidence = {
        'repeats_requested': repeats,
        'repeats_completed': len(attempts),
        'attempts': attempts,
    }
    (run_dir / 'g5-repeated-runs.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=False))
    return ScenarioResult('G5', 'pass', f'Repeated baseline path passed {repeats} times', evidence)


def main() -> int:
    parser = argparse.ArgumentParser(description='Run GUI regression smoke scenarios against the desktop bridge.')
    parser.add_argument('--output-dir', default='artifacts/gui-regression-runs', help='Directory where evidence files are stored')
    parser.add_argument('--title-pattern', default='*Blender*')
    parser.add_argument('--class-name', default='GHOST_WindowClass')
    parser.add_argument('--scenario', action='append', dest='scenarios', help='Scenario id to run (default: G1)')
    parser.add_argument('--repeats', type=int, default=3, help='Repeat count for G5 repeated-run scenario')
    args = parser.parse_args()

    run_id = utc_stamp()
    run_dir = Path(args.output_dir) / run_id
    ensure_dir(run_dir)

    manifest: dict[str, Any] = {
        'run_id': run_id,
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'title_pattern': args.title_pattern,
        'class_name': args.class_name,
        'scenarios_requested': args.scenarios or ['G1'],
        'repeats': args.repeats,
        'results': [],
    }

    try:
        client = BridgeClient.from_env()
        windows_payload = client.list_windows()
        (run_dir / 'windows.json').write_text(json.dumps(windows_payload, indent=2, ensure_ascii=False))
        win = pick_blender_window(windows_payload, args.title_pattern, args.class_name)
        if not win:
            raise BridgeError('No matching Blender window found for requested signature')

        requested = [s.upper() for s in (args.scenarios or ['G1'])]
        for scenario in requested:
            if scenario == 'G1':
                result = scenario_g1_baseline(client, win, run_dir)
            elif scenario == 'G2':
                result = scenario_g2_moved_window(client, win, run_dir, args.title_pattern, args.class_name)
                win = result.evidence['refreshed_window']
            elif scenario == 'G3':
                result = scenario_g3_resized_window(client, win, run_dir, args.title_pattern, args.class_name)
                win = result.evidence['refreshed_window']
            elif scenario == 'G5':
                result = scenario_g5_repeated_runs(client, win, run_dir, args.repeats)
            else:
                result = ScenarioResult(scenario, 'skipped', 'Scenario not implemented yet', {})
            manifest['results'].append(asdict(result))

        manifest['status'] = 'pass' if all(r['status'] == 'pass' for r in manifest['results']) else 'partial'
    except Exception as exc:  # noqa: BLE001
        manifest['status'] = 'fail'
        manifest['error'] = f'{type(exc).__name__}: {exc}'
        (run_dir / 'error.txt').write_text(manifest['error'])
        print(manifest['error'], file=sys.stderr)
    finally:
        manifest['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        (run_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        print(str(run_dir))

    return 0 if manifest['status'] in {'pass', 'partial'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
