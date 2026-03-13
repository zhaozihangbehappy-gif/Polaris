from __future__ import annotations

import json
from pywinauto import Desktop

matches = []
for w in Desktop(backend='uia').windows():
    try:
        title = w.window_text()
        cls = w.class_name()
        if cls in ('#32770', 'NUIDialog') or title in ('Open', '打开', 'Open Delivery File', 'Save', '保存'):
            rect = w.rectangle()
            matches.append({
                'title': title,
                'class_name': cls,
                'handle': int(w.handle),
                'left': rect.left,
                'top': rect.top,
                'right': rect.right,
                'bottom': rect.bottom,
            })
    except Exception:
        pass
print(json.dumps(matches, ensure_ascii=False))
