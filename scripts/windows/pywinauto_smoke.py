from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pywinauto import Desktop


def stamp() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime('%Y%m%dT%H%M%S.%fZ')


def main() -> int:
    run_id = stamp()
    out_dir = Path(r"D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\pywinauto-runs") / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        'run_id': run_id,
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'running',
    }

    try:
        desktop = Desktop(backend='uia')
        windows = []
        for w in desktop.windows():
            try:
                rect = w.rectangle()
                windows.append({
                    'title': w.window_text(),
                    'class_name': w.class_name(),
                    'handle': int(w.handle),
                    'rect': {
                        'left': rect.left,
                        'top': rect.top,
                        'right': rect.right,
                        'bottom': rect.bottom,
                        'width': rect.width(),
                        'height': rect.height(),
                    },
                })
            except Exception:
                continue

        manifest['status'] = 'pass'
        manifest['window_count'] = len(windows)
        manifest['evidence'] = {
            'windows_json': str(out_dir / 'windows.json'),
        }
        (out_dir / 'windows.json').write_text(json.dumps(windows, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception as exc:
        manifest['status'] = 'fail'
        manifest['error'] = f'{type(exc).__name__}: {exc}'
        (out_dir / 'error.txt').write_text(manifest['error'], encoding='utf-8')
    finally:
        manifest['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        (out_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        print(str(out_dir))

    return 0 if manifest['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
