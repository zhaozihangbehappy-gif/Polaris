from __future__ import annotations

import subprocess
import time
from pywinauto import Application, Desktop

# Try classic WordPad if present; otherwise fallback to write.exe launcher
subprocess.Popen([r'C:\Windows\write.exe'])
time.sleep(1.2)
app = Application(backend='uia').connect(path='wordpad.exe')
win = app.top_window()
win.set_focus()
time.sleep(0.3)
try:
    win.menu_select('File->Open')
except Exception:
    win.type_keys('%fo', set_foreground=True)

time.sleep(1.5)
# print visible dialog classes/titles for debugging
items = []
for w in Desktop(backend='uia').windows():
    try:
        if w.window_text() or w.class_name() in ('#32770','NUIDialog'):
            items.append({'title': w.window_text(), 'class_name': w.class_name(), 'handle': int(w.handle)})
    except Exception:
        pass
print(items)
