from __future__ import annotations

import json
from pathlib import Path
from pywinauto import Desktop

out_path = Path(r'D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\gui-template-calibration\desktop-windows-win32.json')
items = []
for w in Desktop(backend='win32').windows():
    try:
        rect = w.rectangle()
        items.append({
            'title': w.window_text(),
            'class_name': w.class_name(),
            'handle': int(w.handle),
            'left': rect.left,
            'top': rect.top,
            'right': rect.right,
            'bottom': rect.bottom,
        })
    except Exception:
        pass
out_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')
print(str(out_path))
