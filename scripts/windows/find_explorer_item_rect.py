from __future__ import annotations

import json
from pywinauto import Desktop

TARGET_WINDOW = r"D:\Administrator\Documents\Playground\openclaw-upstream\artifacts\delivery"
TARGET_ITEM = "cabinet-12cell-concept.blend"


def main() -> int:
    desktop = Desktop(backend='uia')
    win = desktop.window(title=TARGET_WINDOW)
    win.wait('exists ready', timeout=6)
    descendants = win.descendants(control_type='ListItem')
    for item in descendants:
        try:
            if item.window_text() == TARGET_ITEM:
                rect = item.rectangle()
                out = {
                    'window_title': TARGET_WINDOW,
                    'item_title': TARGET_ITEM,
                    'rect': {
                        'left': rect.left,
                        'top': rect.top,
                        'right': rect.right,
                        'bottom': rect.bottom,
                        'width': rect.width(),
                        'height': rect.height(),
                        'center_x': rect.left + rect.width() // 2,
                        'center_y': rect.top + rect.height() // 2,
                    }
                }
                print(json.dumps(out, ensure_ascii=False))
                return 0
        except Exception:
            continue
    raise SystemExit('item_not_found')

if __name__ == '__main__':
    raise SystemExit(main())
