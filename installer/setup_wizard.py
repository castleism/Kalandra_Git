"""
INSTALLER/SETUP_WIZARD.PY — the Kalandra-Setup.exe front door.

Compiled to a single .exe with PyInstaller (launchers\\"Build Setup
EXE.bat"), so a fresh machine needs NOTHING preinstalled to run it — the
exe carries its own Python. It is a proper wizard:

  1. Welcome (owl icon, version)
  2. DETECTION — existing install in this folder OR anywhere on the
     machine (desktop shortcut's working directory)
  3. Choice: Repair / Uninstall the found copy, or Fresh install here
  4. Delegates the heavy lifting to the proven PowerShell machinery
     (Kalandra-Setup.ps1 / Kalandra-Uninstall.ps1) in a visible console.

Pure stdlib (tkinter), so PyInstaller bundles it cleanly.
"""

import os
import subprocess
import sys
import tkinter as tk

BG, GOLD, TEXT, MUTED = "#0c0e12", "#c8aa6e", "#e8e6df", "#9aa4b2"


def app_root():
    """Folder the exe/script lives in (installer/ -> parent)."""
    if getattr(sys, "frozen", False):
        here = os.path.dirname(sys.executable)
    else:
        here = os.path.dirname(os.path.abspath(__file__))
    # exe sits at repo root; script sits in installer/
    return here if os.path.exists(os.path.join(here, "version.py")) \
        else os.path.dirname(here)


def find_existing(root):
    """-> path of an existing install, or None. Checks, in order: this
    folder's runtime data, the HKCU registry marker (written at install,
    removed at uninstall — the real 'is it installed?'), and finally the
    desktop shortcut as a legacy fallback."""
    if os.path.exists(os.path.join(root, "data_engine", "config.json")) or \
       os.path.exists(os.path.join(root, "data_engine",
                                   "localized_knowledge.db")):
        return root
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Kalandra") as k:
            d, _ = winreg.QueryValueEx(k, "InstallPath")
        if d and os.path.exists(os.path.join(d, "version.py")) and \
                os.path.normcase(d.rstrip("\\/")) != \
                os.path.normcase(root.rstrip("\\/")):
            return d
    except Exception:
        pass
    try:
        ps = ("$p=[Environment]::GetFolderPath('Desktop')+'\\Kalandra.lnk';"
              "if (Test-Path $p) { $s=(New-Object -ComObject WScript.Shell)"
              ".CreateShortcut($p); $d=$s.WorkingDirectory; if ($d -and "
              "(Test-Path (Join-Path $d 'version.py'))) { $d } }")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=15)
        d = (out.stdout or "").strip()
        if d and os.path.normcase(d.rstrip("\\/")) != \
                os.path.normcase(root.rstrip("\\/")):
            return d
    except Exception:
        pass
    return None


def run_ps1(path, cwd):
    """Run a PowerShell script in a visible console and wait."""
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-File", path], cwd=cwd,
                   creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


class Wizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.root_dir = app_root()
        self.title("Kalandra Setup")
        self.configure(bg=BG)
        try:
            ico = os.path.join(self.root_dir, "gui_overlay", "assets",
                               "kalandra.ico")
            if os.path.exists(ico):
                self.iconbitmap(ico)
        except Exception:
            pass
        self.body = tk.Frame(self, bg=BG)
        self.body.pack(fill="both", expand=True, padx=28, pady=24)
        self.page_welcome()
        # Fit-to-content, clamped to the screen, centered.
        self.update_idletasks()
        w = max(560, self.body.winfo_reqwidth() + 56)
        h = max(360, self.body.winfo_reqheight() + 48)
        w = min(w, self.winfo_screenwidth() - 80)
        h = min(h, self.winfo_screenheight() - 80)
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 3
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(520, 340)

    # ---------- helpers ----------
    def clear(self):
        for c in self.body.winfo_children():
            c.destroy()

    def head(self, text):
        tk.Label(self.body, text=text, fg=GOLD, bg=BG,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w")

    def para(self, text):
        tk.Label(self.body, text=text, fg=TEXT, bg=BG, justify="left",
                 wraplength=520, font=("Segoe UI", 10)).pack(anchor="w",
                                                             pady=(10, 0))

    def button(self, text, cmd, accent=False):
        b = tk.Button(self.body, text=text, command=cmd,
                      bg=(GOLD if accent else "#1b212b"),
                      fg=("#0c0e12" if accent else TEXT),
                      activebackground="#f0d9a8", relief="flat",
                      font=("Segoe UI", 11, "bold" if accent else "normal"),
                      padx=18, pady=8, cursor="hand2")
        b.pack(fill="x", pady=(12, 0))
        return b

    # ---------- pages ----------
    def page_welcome(self):
        self.clear()
        self.head("Kalandra — Path of Exile 2 Companion")
        self.para("The mirror, the orb and the owl: an AI guide that makes "
                  "PoE2 accessible — build planning, price checking, "
                  "crafting plans and walkthroughs, grounded in your own "
                  "Path of Building data.")
        self.button("Continue", self.page_detect, accent=True)
        self.button("Exit", self.destroy)

    def page_detect(self):
        self.clear()
        found = find_existing(self.root_dir)
        if found:
            self.head("Existing installation detected")
            self.para(f"Found at:\n{found}\n\nWhat would you like to do?")
            self.button("Repair / Uninstall that copy",
                        lambda: self.run_uninstaller(found), accent=True)
            self.button("Fresh install here anyway", self.page_install)
            self.button("Exit", self.destroy)
        else:
            self.head("No existing installation found")
            self.para("This looks like a fresh machine. The installer will "
                      "set up Python, all dependencies, the add-ons you "
                      "choose, and register Kalandra as a searchable "
                      "installed program (Start menu, desktop, and Apps).")
            self.button("Install Kalandra", self.page_install, accent=True)
            self.button("Exit", self.destroy)

    def run_uninstaller(self, where):
        ps1 = os.path.join(where, "installer", "Kalandra-Uninstall.ps1")
        self.clear()
        if os.path.exists(ps1):
            self.head("Repair / Uninstall running…")
            self.para("Answer the prompts in the console window. Re-run "
                      "this setup afterwards for a fresh install.")
            self.update()
            run_ps1(ps1, where)
            self.page_detect()
        else:
            self.head("That copy has no uninstaller")
            self.para("It predates the Repair/Uninstall tool — remove it "
                      "manually, or run its own Setup.")
            self.button("Back", self.page_detect)

    def page_install(self):
        ps1 = os.path.join(self.root_dir, "installer", "Kalandra-Setup.ps1")
        self.clear()
        self.head("Installing…")
        self.para("The dependency installer opens next: tick what you want, "
                  "point at your tools, and it wires everything up. Close "
                  "it when done and launch Kalandra from the desktop "
                  "shortcut.")
        self.update()
        if os.path.exists(ps1):
            run_ps1(ps1, self.root_dir)
            # Register Kalandra as a real installed program: Start Menu entry
            # (so it's findable from the Start/home search), Apps & Features
            # listing, and the desktop shortcut.
            shortcut_ps1 = os.path.join(self.root_dir, "installer",
                                        "Make-Shortcut.ps1")
            if os.path.exists(shortcut_ps1):
                try:
                    run_ps1(shortcut_ps1, self.root_dir)
                except Exception:
                    pass
            self.head("Setup finished")
            self.para("Kalandra is installed. Press the Start/home button and "
                      "type \"Kalandra\" to launch it — it's also on your "
                      "desktop and in Settings > Apps. Fly free, exile.")
            self.button("Close", self.destroy, accent=True)
        else:
            self.para("installer\\Kalandra-Setup.ps1 is missing — this copy "
                      "is incomplete. Re-extract the release zip.")
            self.button("Close", self.destroy)


if __name__ == "__main__":
    Wizard().mainloop()
