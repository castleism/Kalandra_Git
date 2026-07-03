"""
GUI_OVERLAY/LOG_BUS.PY
A single, app-wide log bus. Everything Kalandra does on the backend funnels
through here: the console logger pushes every event to it, and the dashboard's
Terminal tab subscribes for live, fully transparent visibility.

- LOG_BUS.push(category, message)  -> records + emits (safe from any thread)
- LOG_BUS.emitted (pyqtSignal)     -> (timestamp, category, message)
- LOG_BUS.history                  -> recent events so a newly-opened terminal
                                      can show what already happened.

It degrades to a no-op if PyQt isn't available, so importing it is always safe.
"""

from collections import deque
from datetime import datetime

try:
    from PyQt6.QtCore import QObject, pyqtSignal
    _QT = True
except Exception:
    _QT = False

# Map the many raw categories to a few user-friendly filter groups.
GROUPS = {
    "Database":      {"DATABASE", "STARTUP", "SYNC"},
    "GUI / Actions": {"SYSTEM", "GUI", "SHUTDOWN"},
    "Voice & AI":    {"VOICE", "CHAT", "AI-CONTEXT"},
    "Build / PoB":   {"POB"},
    "Capture":       {"OCR", "RECORD"},
}
GROUP_ORDER = ["Database", "Voice & AI", "Build / PoB", "GUI / Actions", "Capture", "Other"]


def group_for(category):
    cat = (category or "").upper()
    for grp, cats in GROUPS.items():
        if cat in cats:
            return grp
    return "Other"


if _QT:
    class _LogBus(QObject):
        emitted = pyqtSignal(str, str, str)   # timestamp, category, message

        def __init__(self):
            super().__init__()
            self.history = deque(maxlen=4000)

        def push(self, category, message):
            ts = datetime.now().strftime("%H:%M:%S")
            cat = str(category) if category is not None else ""
            msg = str(message) if message is not None else ""
            self.history.append((ts, cat, msg))
            try:
                self.emitted.emit(ts, cat, msg)
            except Exception:
                pass

    LOG_BUS = _LogBus()
else:
    class _NoopBus:
        emitted = None

        def __init__(self):
            self.history = deque(maxlen=4000)

        def push(self, category, message):
            ts = datetime.now().strftime("%H:%M:%S")
            self.history.append((ts, str(category), str(message)))

    LOG_BUS = _NoopBus()
