"""
TESTS/SETTINGS_LAYOUT_CHECKS.PY
Source-level checks for the Settings-menu redesign (2026-07-12): everyday
settings up top at full size; Oracle setup (API key/budget) and account
linking in CollapsibleSections — open on first run, collapsed once configured,
NEVER hidden. The sandbox has no GPU/EGL so PyQt can't render here; like the
stress suite's AST audit, these checks read the source (parse + inspect)
instead of instantiating widgets. Run:
    python tests/settings_layout_checks.py
Exit code 0 = all green.
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "gui_overlay", "mirror_window.py")

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  XX  {name}")


def find_class(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def methods(cls):
    return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}


def src_of(node, text):
    return ast.get_source_segment(text, node) or ""


def main():
    text = open(SRC, encoding="utf-8").read()
    # The file must still be valid Python at all (py_compile equivalent).
    tree = ast.parse(text)
    check("mirror_window.py parses", True)

    # --- CollapsibleSection widget --------------------------------------------
    cs = find_class(tree, "CollapsibleSection")
    check("CollapsibleSection class exists", cs is not None)
    if cs is not None:
        m = methods(cs)
        check("has set_status / set_collapsed / _sync",
              {"set_status", "set_collapsed", "_sync"} <= set(m))
        sc = src_of(m.get("set_collapsed"), text)
        check("auto-collapse respects a user's manual toggle",
              "_user_touched" in sc and "auto" in sc)
        sy = src_of(m.get("_sync"), text)
        check("collapsed body is hidden, not removed",
              "setVisible" in sy and "deleteLater" not in src_of(cs, text))
        check("header shows expand arrow both ways", "▸" in sy and "▾" in sy)

    sd = find_class(tree, "SettingsDialog")
    check("SettingsDialog class exists", sd is not None)
    if sd is None:
        print(f"\nsettings_layout: {PASS} passed, {FAIL} failed")
        return 1
    sdm = methods(sd)
    bui = src_of(sdm.get("_build_ui"), text)

    # --- structure: everyday settings up top, set-once stuff collapsible -------
    check("old cluttered title is gone", "Oracle Setup &amp; Account Linking" not in bui)
    check("Oracle section is a CollapsibleSection",
          "self.oracle_sec = CollapsibleSection(" in bui)
    check("Accounts section is a CollapsibleSection",
          "self.accounts_sec = CollapsibleSection(" in bui)
    check("Oracle open-on-first-run flag wired",
          "settings_oracle_done" in bui)
    check("Accounts open-on-first-run flag wired",
          "settings_accounts_done" in bui)
    # The everyday rows must still be added straight to the dialog body (root),
    # NOT foldered away: brain/model, voice, orb, sync speed, price checker.
    check("AI brain row stays top-level", "root.addLayout(brain_row)" in bui)
    check("voice row stays top-level", "root.addLayout(voice_row)" in bui)
    check("sync-speed row stays top-level", "root.addLayout(speed_row)" in bui)
    check("price-checker row stays top-level", "root.addLayout(pc_row)" in bui)
    # The set-once rows must live INSIDE the Oracle section now.
    check("API key row moved into Oracle section", "osec.addLayout(key_row)" in bui)
    check("budget row moved into Oracle section", "osec.addLayout(budget_row)" in bui)
    check("key row no longer top-level", "root.addLayout(key_row)" not in bui)
    # Service rows must feed the accounts section, not the bare grid.
    check("service rows go into the accounts section",
          "acc.addWidget(self._service_row(svc))" in bui
          and "grid.addWidget(self._service_row(svc))" not in bui)
    check("both sections land in the scroll area",
          "grid.addWidget(self.oracle_sec)" in bui
          and "grid.addWidget(self.accounts_sec)" in bui)
    # Nothing hidden: dashboard/custom tab pickers still built.
    check("dashboard tabs picker still built",
          "_build_dashboard_tabs_section(grid)" in bui)
    check("custom tabs picker still built",
          "_build_custom_tabs_section(grid)" in bui)

    # --- collapsed-once-set wiring ---------------------------------------------
    ac = src_of(sdm.get("_apply_connections"), text)
    check("_apply_connections updates the accounts header count",
          "accounts_sec.set_status" in ac)
    check("first linked account marks accounts configured",
          "settings_accounts_done" in ac and "save_config" in ac)
    sk = src_of(sdm.get("_set_ai_key_state"), text) if "_set_ai_key_state" in sdm else ""
    check("_set_ai_key_state exists and updates the Oracle header",
          "oracle_sec.set_status" in sk)
    check("saved key marks Oracle configured",
          "settings_oracle_done" in sk and "save_config" in sk)
    sv = src_of(sdm.get("_save_ai_key"), text)
    check("manual key save also marks Oracle configured",
          "settings_oracle_done" in sv)
    cl = src_of(sdm.get("_clear_ai_key"), text)
    check("clearing the key resets the Oracle header", "set_status" in cl)

    # --- unbound-name audit for the new widget (sandbox can't render Qt) -------
    # Every bare Name loaded inside CollapsibleSection must resolve somewhere:
    # builtins, module-level import/assignment, class/self scope, or args.
    import builtins
    module_names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                module_names.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ClassDef):
            module_names.add(node.name)
        elif isinstance(node, ast.FunctionDef):
            module_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    module_names.add(t.id)
    unbound = set()
    if cs is not None:
        for fn in methods(cs).values():
            local = {a.arg for a in fn.args.args}
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name):
                            local.add(t.id)
            for node in ast.walk(fn):
                if (isinstance(node, ast.Name)
                        and isinstance(node.ctx, ast.Load)
                        and node.id not in local
                        and node.id not in module_names
                        and not hasattr(builtins, node.id)):
                    unbound.add(node.id)
    check(f"no unbound names in CollapsibleSection {sorted(unbound) or ''}",
          not unbound)

    print(f"\nsettings_layout: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
