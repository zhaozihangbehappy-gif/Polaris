from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pywinauto import Desktop

OUT_DIR = Path(r"D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\gui-template-calibration")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def stamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')


def rect_dict(rect: Any) -> dict[str, int]:
    return {
        'left': rect.left,
        'top': rect.top,
        'right': rect.right,
        'bottom': rect.bottom,
        'width': rect.width(),
        'height': rect.height(),
        'center_x': rect.left + rect.width() // 2,
        'center_y': rect.top + rect.height() // 2,
    }


def find_window(title: str):
    desktop = Desktop(backend='uia')
    matches = []
    for w in desktop.windows():
        try:
            if w.window_text() == title:
                rect = w.rectangle()
                matches.append((w, rect.width() * rect.height()))
        except Exception:
            continue
    if not matches:
        raise RuntimeError(f'No window found for title: {title}')
    for w, _ in matches:
        try:
            if w.has_focus():
                return w
        except Exception:
            continue
    matches.sort(key=lambda pair: pair[1], reverse=True)
    return matches[0][0]


def explorer_select_file(path_str: str, file_name: str) -> dict[str, Any]:
    win = find_window(path_str)
    data: dict[str, Any] = {
        'template': 'explorer_select_file',
        'window_title': path_str,
        'window_rect': rect_dict(win.rectangle()),
        'file_name': file_name,
    }
    search = None
    for ctrl in win.descendants(control_type='Edit'):
        try:
            title = ctrl.window_text()
            auto_id = getattr(ctrl.element_info, 'automation_id', '')
            if '搜索' in title or 'Search' in title or auto_id in ('SearchEditBox', 'SearchControlHost'):
                search = ctrl
                break
        except Exception:
            continue
    if search is None:
        edits = win.descendants(control_type='Edit')
        if edits:
            search = edits[-1]
    if search is not None:
        data['search_rect'] = rect_dict(search.rectangle())
    item = None
    for ctrl in win.descendants(control_type='ListItem'):
        try:
            if ctrl.window_text() == file_name:
                item = ctrl
                break
        except Exception:
            continue
    if item is not None:
        data['item_rect'] = rect_dict(item.rectangle())
    return data


def blender_focus() -> dict[str, Any]:
    # Source 1: bridge-captured windows persisted from WSL side.
    bridge_windows = Path(r'D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\gui-template-calibration\desktop-windows.json')
    if bridge_windows.exists():
        try:
            items = json.loads(bridge_windows.read_text(encoding='utf-8'))
            for item in items:
                title = str(item.get('title', ''))
                if 'Blender' in title and item.get('class_name') == 'GHOST_WindowClass':
                    return {
                        'template': 'blender_focus',
                        'window_title': title,
                        'window_rect': {
                            'left': item['left'], 'top': item['top'], 'right': item['right'], 'bottom': item['bottom'],
                            'width': item['right'] - item['left'], 'height': item['bottom'] - item['top'],
                            'center_x': (item['left'] + item['right']) // 2,
                            'center_y': (item['top'] + item['bottom']) // 2,
                        },
                    }
        except Exception:
            pass
    # Source 2: native blender process main window.
    try:
        import subprocess
        ps_script = r'C:\Users\Administrator\.openclaw\workspace\scripts\windows\list_blender_windows.ps1'
        raw_bytes = subprocess.check_output([
            'powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File', ps_script
        ], timeout=10)
        raw = None
        for enc in ('utf-8', 'utf-16le', 'gbk', 'cp936'):
            try:
                raw = raw_bytes.decode(enc).strip()
                break
            except Exception:
                pass
        if raw is None:
            raw = raw_bytes.decode('utf-8', errors='replace').strip()
        if raw and raw != 'null':
            data = json.loads(raw)
            items = data if isinstance(data, list) else [data]
            for item in items:
                title = str(item.get('MainWindowTitle', ''))
                if 'Blender' in title:
                    return {
                        'template': 'blender_focus',
                        'window_title': title,
                        'window_rect': {
                            'left': 0, 'top': 0, 'right': 2560, 'bottom': 1440,
                            'width': 2560, 'height': 1440,
                            'center_x': 1280, 'center_y': 720,
                        },
                    }
    except Exception:
        pass
    # Source 3: UIA desktop windows.
    desktop = Desktop(backend='uia')
    candidates = []
    for w in desktop.windows():
        try:
            title = w.window_text()
            if 'Blender' in title:
                candidates.append(w)
        except Exception:
            continue
    if not candidates:
        raise RuntimeError('No Blender window found')
    win = candidates[0]
    return {
        'template': 'blender_focus',
        'window_title': win.window_text(),
        'window_rect': rect_dict(win.rectangle()),
    }


def file_dialog_select_file(file_name: str) -> dict[str, Any]:
    desktop = Desktop(backend='win32')
    dlg = None
    candidates = []
    for w in desktop.windows():
        try:
            title = w.window_text()
            cls = w.class_name()
            if cls == '#32770' and title in ('打开', 'Open', '保存', 'Save'):
                candidates.append(w)
                continue
            if cls == '#32770' and title:
                candidates.append(w)
        except Exception:
            continue
    if not candidates:
        raise RuntimeError('No file dialog found')
    for w in candidates:
        try:
            if w.has_focus():
                dlg = w
                break
        except Exception:
            continue
    if dlg is None:
        dlg = candidates[0]
    data = {
        'template': 'file_dialog_select_file',
        'window_title': dlg.window_text(),
        'window_rect': rect_dict(dlg.rectangle()),
        'file_name': file_name,
    }
    edits = []
    try:
        edits = dlg.descendants(class_name='Edit')
    except Exception:
        pass
    if edits:
        data['filename_edit_rect'] = rect_dict(edits[-1].rectangle())
    button = None
    for ctrl in dlg.descendants():
        try:
            text = ctrl.window_text()
            cls = ctrl.class_name()
            if cls == 'Button' and text in ('打开(O)', '打开', 'Open', '保存(S)', '保存', 'Save'):
                button = ctrl
                break
        except Exception:
            continue
    if button is not None:
        data['confirm_button_rect'] = rect_dict(button.rectangle())
    return data


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit('missing template kind')
    kind = sys.argv[1]
    run_id = stamp()
    out_path = OUT_DIR / f'{kind}-{run_id}.json'
    result: dict[str, Any] = {
        'run_id': run_id,
        'kind': kind,
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'running',
    }
    try:
        if kind == 'explorer_select_file':
            payload = explorer_select_file(sys.argv[2], sys.argv[3])
        elif kind == 'explorer_open_file':
            payload = explorer_select_file(sys.argv[2], sys.argv[3])
            payload['template'] = 'explorer_open_file'
        elif kind == 'blender_focus':
            payload = blender_focus()
        elif kind == 'file_dialog_select_file':
            payload = file_dialog_select_file(sys.argv[2])
        else:
            raise SystemExit(f'unknown template kind: {kind}')
        result['status'] = 'pass'
        result['payload'] = payload
    except Exception as exc:  # noqa: BLE001
        result['status'] = 'fail'
        result['error'] = f'{type(exc).__name__}: {exc}'
    finally:
        result['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(str(out_path))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
