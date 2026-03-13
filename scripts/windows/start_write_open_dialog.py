from __future__ import annotations

import subprocess
import time
from pywinauto import Application

subprocess.Popen([r'C:\Windows\System32\write.exe'])
time.sleep(1.2)
app = Application(backend='uia').connect(path='wordpad.exe')
win = app.top_window()
try:
    win.set_focus()
except Exception:
    pass
try:
    win.type_keys('^o', set_foreground=True)
except Exception:
    try:
        win.menu_select('File->Open')
    except Exception as exc:
        raise SystemExit(f'failed_to_open_dialog: {exc}')
time.sleep(1.5)
print('WRITE_OPEN_DIALOG_STARTED')
