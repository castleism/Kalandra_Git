"""
CONFIGURE.PY  --  tiny helper the installer's configuration page calls to store
account secrets in the SAME secure OS keychain the overlay reads from
(core_engine.account_manager -> keyring). Paths/non-secrets are written to
config.json by the installer directly; this script only handles secrets.

Usage:
    python configure.py set-secret <service> [value]   # value via arg OR stdin
    python configure.py status                          # list services + connected
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/ -> repo root
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main():
    args = sys.argv[1:]
    try:
        from core_engine.account_manager import AccountManager, SERVICES
    except Exception as e:
        print(f"account manager unavailable: {e}")
        return 1
    am = AccountManager()

    if not args:
        print("usage: configure.py set-secret <service> [value] | status")
        return 1

    if args[0] == "status":
        print(am.storage_note())
        for s in am.list_services():
            flag = "connected" if s["connected"] else "--"
            print(f"[{flag}] {s['id']}: {s['name']} ({s['kind']})")
        return 0

    if args[0] == "set-secret" and len(args) >= 2:
        service = args[1]
        EXTRA = {"poesessid"}   # stored as a secret but not a listed SERVICE
        if service not in SERVICES and service not in EXTRA:
            print(f"unknown service '{service}'. Known: {', '.join(list(SERVICES) + list(EXTRA))}")
            return 1
        value = args[2] if len(args) >= 3 else sys.stdin.read()
        value = (value or "").strip()
        ok = am.set_secret(service, value)
        if ok and value:
            print(f"OK: stored secret for {service} in the OS keychain.")
        elif ok and not value:
            print(f"OK: cleared secret for {service}.")
        else:
            print("FAILED: keyring unavailable (pip install keyring) — secret not stored.")
        return 0 if ok else 1

    print("usage: configure.py set-secret <service> [value] | status")
    return 1


if __name__ == "__main__":
    sys.exit(main())
