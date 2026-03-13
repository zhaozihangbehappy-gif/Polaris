from __future__ import annotations

import time
from pywinauto import Application

app = Application(backend='uia').start('notepad.exe')
time.sleep(0.8)
win = app.window(title_re='.*Notepad')
win.wait('exists ready', timeout=10)
try:
    win.menu_select('File->Open')
except Exception:
    try:
        win.type_keys('%fo', set_foreground=True)
    except Exception as exc:
        raise SystemExit(f'failed_to_open_dialog: {exc}')
time.sleep(1.2)
print('NOTEPAD_OPEN_DIALOG_STARTED')
