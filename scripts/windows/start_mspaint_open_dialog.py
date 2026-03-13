from __future__ import annotations

import subprocess
import time
from pywinauto import Application

subprocess.Popen([r'C:\Windows\System32\mspaint.exe'])
time.sleep(1.5)
app = Application(backend='uia').connect(path='mspaint.exe')
win = app.top_window()
try:
    win.set_focus()
except Exception:
    pass
# Prefer direct accelerator for Open dialog
try:
    win.type_keys('^o', set_foreground=True)
except Exception:
    try:
        win.type_keys('%fo', set_foreground=True)
    except Exception as exc:
        raise SystemExit(f'failed_to_open_dialog: {exc}')
time.sleep(1.8)
print('MSPAINT_OPEN_DIALOG_STARTED')
