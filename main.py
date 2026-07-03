"""
MAIN.PY  —  Kalandra Overlay entry point.

On launch it:
  1. Verifies the real system date/time.
  2. Runs a lightweight freshness check (is the local database up to date vs poe2db?).
  3. Launches the transparent Mirror overlay.

Run with:  python main.py
"""

import os
import sys
import traceback

# Make sure imports resolve regardless of where we're launched from.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def run_startup_checks():
    """Date/time + database freshness. Never fatal — only informative."""
    print("=========================================================")
    print("            KALANDRA OVERLAY — STARTUP CHECKS")
    print("=========================================================")
    db = None
    try:
        from core_engine.database_handler import KalandraDBHandler
        db = KalandraDBHandler()
    except Exception as e:
        print(f"[STARTUP] Database unavailable: {e}")

    time_matrix = None
    try:
        from core_engine.time_matrix import KalandraTimeMatrix
        time_matrix = KalandraTimeMatrix()
        print(f"[STARTUP] System date/time: {time_matrix.get_formatted_local_time()}")
    except Exception as e:
        print(f"[STARTUP] Time matrix unavailable: {e}")

    try:
        from core_engine.data_sources import FreshnessChecker
        fc = FreshnessChecker(db_handler=db, time_matrix=time_matrix,
                              logger=lambda c, m: print(f"[{c}] {m}"))
        report = fc.run_startup_check(online=True)
        print(f"[STARTUP] Last sync: {report['last_sync']}")
        print(f"[STARTUP] Stored version: {report['stored_version']} | "
              f"Live: {report.get('live_version', 'unknown')}")
        if report.get("needs_sync"):
            print("[STARTUP] >> Database looks out of date or empty. "
                  "Click the blue (top-center) medallion to sync from poe2db.")
        for s in report["sources"]:
            print(f"[STARTUP]   source {s['name']:<12} {s['status']}  ({s['url']})")
    except Exception as e:
        print(f"[STARTUP] Freshness check skipped: {e}")

    if db is not None:
        try:
            db.close()
        except Exception:
            pass
    print("=========================================================\n")


def main():
    run_startup_checks()
    try:
        from gui_overlay.mirror_window import KalandraOverlayApp, PYQT_AVAILABLE
        if not PYQT_AVAILABLE:
            print("FATAL: PyQt6 is not installed. Run: pip install PyQt6")
            input()
            return 1
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QTimer, Qt
        # Required before QApplication for Qt WebEngine (dashboard web tabs);
        # also prevents a class of GPU-context crashes.
        try:
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
        except Exception:
            pass
        app = QApplication(sys.argv)
        # The overlay is a Tool window; Qt would otherwise quit when the last
        # NON-tool window (the dashboard) closes. Keep the app alive and let the
        # overlay own the exit.
        app.setQuitOnLastWindowClosed(False)
        overlay = KalandraOverlayApp()
        overlay.show()
        QTimer.singleShot(800, overlay.initial_sync)
        QTimer.singleShot(1200, overlay.startup_freshness_check)
        QTimer.singleShot(1600, overlay.startup_game_data_check)
        code = app.exec()
        print("\nKalandra overlay closed cleanly.")
        return code
    except Exception:
        print("\nCRITICAL RUNTIME EXCEPTION:")
        traceback.print_exc()
        input("Press Enter to close...")
        return 1


if __name__ == "__main__":
    sys.exit(main())
