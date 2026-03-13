from __future__ import annotations

import json
from pathlib import Path
from pywinauto import Desktop

out = []
for w in Desktop(backend='uia').windows():
    try:
        if w.class_name().startswith('WindowsForms10.Window'):
            children = []
            for c in w.descendants(depth=2):
                try:
                    r = c.rectangle()
                    children.append({
                        'title': c.window_text(),
                        'class_name': c.class_name(),
                        'control_type': getattr(c.element_info, 'control_type', None),
                        'automation_id': getattr(c.element_info, 'automation_id', None),
                        'left': r.left, 'top': r.top, 'right': r.right, 'bottom': r.bottom,
                    })
                except Exception:
                    pass
            out.append({'title': w.window_text(), 'class_name': w.class_name(), 'handle': int(w.handle), 'children': children})
    except Exception:
        pass
p = Path(r'D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\gui-template-calibration\windowsforms-dialog-probe.json')
p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
print(str(p))
