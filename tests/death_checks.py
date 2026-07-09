"""
TESTS/DEATH_CHECKS.PY — sandbox checks for the death-review engine (W4-21).

Covers Client.txt parsing, the log tailer, the defensive audit rules, the
incident store, the reports, and the OBS auth/fail-soft plumbing. No OBS,
no network, no Qt — pure engine.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def guard(name, fn):
    """fn must not raise."""
    try:
        fn()
        check(name, True)
    except Exception as e:
        print(f"  [FAIL] {name}: raised {e}")
        globals()["FAIL"] += 1


from core_engine import death_review as dr
from core_engine.obs_bridge import ObsClient, ObsError, build_auth, capture_replay

L = "2026/07/05 12:00:01 123456 cff945b9 [INFO Client 12345] : "

# ---- parse_log_line --------------------------------------------------------
ev = dr.parse_log_line(L + "You have been slain.")
check("self death parsed", ev and ev["kind"] == "death" and ev["who"] == "you")
ev = dr.parse_log_line(L + "Kalandra_Fan has been slain.")
check("party death parsed", ev and ev["who"] == "Kalandra_Fan")
ev = dr.parse_log_line(L + "You have entered Ogham Village.")
check("zone parsed", ev and ev["kind"] == "zone" and ev["zone"] == "Ogham Village")
check("chatter ignored", dr.parse_log_line(L + "gg wp everyone") is None)
check("non-chat line ignored", dr.parse_log_line("[DEBUG] shader compile 34ms") is None)
check("junk-safe", dr.parse_log_line(None) is None)
check("slain in chat text not a death",
      dr.parse_log_line(L + "that boss has been slaying me all day") is None)

# ---- ClientLogWatcher ------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    lp = os.path.join(td, "Client.txt")
    with open(lp, "w", encoding="utf-8") as f:
        f.write(L + "You have entered Old Town.\n")     # history: must NOT replay
    w = dr.ClientLogWatcher(lp)
    check("no replay of history", w.poll() == [])
    with open(lp, "a", encoding="utf-8") as f:
        f.write(L + "You have entered Red Vale.\n")
        f.write(L + "You have been slain.\n")
    evs = w.poll()
    check("two new events", len(evs) == 2)
    check("death carries zone context",
          evs[1]["kind"] == "death" and evs[1]["zone_at"] == "Red Vale")
    check("recent context kept", len(w.recent) == 2)
    with open(lp, "w", encoding="utf-8") as f:          # rotation/truncation
        f.write(L + "You have been slain.\n")
    evs = w.poll()
    check("survives truncation", len(evs) == 1 and evs[0]["kind"] == "death")
    check("missing file fails soft",
          dr.ClientLogWatcher(os.path.join(td, "gone.txt")).poll() == [])

# ---- defensive_audit -------------------------------------------------------
capped = {"FireResist": "75", "ColdResist": "76", "LightningResist": "75",
          "ChaosResist": "35", "Life": "5200", "TotalEHP": "9000",
          "Armour": "22000"}
check("capped build passes clean", dr.defensive_audit(capped, level=90) == [])
f = dr.defensive_audit({"FireResist": "52"}, level=None)
check("uncapped fire flagged", f and "Fire resistance 52%" in f[0]["title"])
check("big gap is critical", f[0]["sev"] == "critical")
f = dr.defensive_audit({"FireResist": "71"})
check("small gap is warn only", f and f[0]["sev"] == "warn")
f = dr.defensive_audit({"ChaosResist": "-30", "ColdResist": "70"})
check("negative chaos critical + sorted first",
      f[0]["sev"] == "critical" and "Chaos" in f[0]["title"])
f = dr.defensive_audit({"Life": "2100", "EnergyShield": "0"}, level=78)
check("thin pool flagged at level", any("pool" in x["title"].lower() for x in f))
check("thin pool NOT flagged when leveling",
      dr.defensive_audit({"Life": "900"}, level=30) == [])
f = dr.defensive_audit({"Armour": "500", "Evasion": "300", "EnergyShield": "100"})
check("no-layer warning", any("mitigation layer" in x["title"] for x in f))
f = dr.defensive_audit({"BlockChance": "8"})
check("token block noted", f and f[0]["sev"] == "note")
f = dr.defensive_audit({"PhysicalMaximumHitTaken": "2400"})
check("one-shot window flagged", f and "Max physical hit" in f[0]["title"])
check("absent stats stay silent", dr.defensive_audit({}) == [])
guard("junk stat values", lambda: dr.defensive_audit(
    {"FireResist": "banana", "Life": None, "ChaosResist": ["?"]}, level="x"))

# ---- incidents on disk -----------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    dr.DEATHS_DIR = os.path.join(td, "deaths")   # redirect the store
    clip = os.path.join(td, "replay.mp4")
    with open(clip, "wb") as fh:
        fh.write(b"\x00" * 64)
    rec = dr.save_incident(
        {"kind": "death", "who": "you", "zone_at": "Red Vale", "ts": 1.0},
        clip_path=clip, clip_msg="saved",
        context=[{"kind": "zone", "raw": "You have entered Red Vale."}])
    check("incident has zone", rec["zone"] == "Red Vale")
    check("clip copied next to record",
          rec["clip"] and rec["clip"].startswith(dr.DEATHS_DIR)
          and os.path.exists(rec["clip"]))
    got = dr.recent_incidents()
    check("round trip", len(got) == 1 and got[0]["zone"] == "Red Vale")
    rec2 = dr.save_incident({"kind": "death", "who": "you"},
                            clip_path=None, clip_msg="OBS off")
    check("no-clip incident honest", rec2["clip"] is None
          and rec2["clip_note"] == "OBS off")

    # ---- reports -----------------------------------------------------------
    fnd = dr.defensive_audit({"FireResist": "52", "ChaosResist": "-10"})
    md = dr.autopsy_markdown(rec, fnd)
    check("md names zone", "Red Vale" in md)
    check("md lists findings", "Fire resistance 52%" in md)
    check("md carries context", "You have entered Red Vale." in md)
    md2 = dr.autopsy_markdown(rec2, [])
    check("clean audit is honest", "No defensive gaps found" in md2)
    p = dr.ai_autopsy_prompt(rec, fnd, build_summary="Witch lvl 80")
    check("prompt carries gaps", "Fire resistance 52%" in p)
    check("prompt carries build", "Witch lvl 80" in p)
    check("prompt demands honesty", "say so honestly" in p)

# ---- OBS plumbing (no OBS needed) ------------------------------------------
a1 = build_auth("hunter2", "salt", "challenge")
a2 = build_auth("hunter2", "salt", "challenge")
a3 = build_auth("hunter2", "SALT", "challenge")
check("auth deterministic", a1 == a2)
check("auth salt-sensitive", a1 != a3)
check("auth is b64 sha256", len(a1) == 44 and a1.endswith("="))
path, msg = capture_replay(host="127.0.0.1", port=59999)   # nothing listening
check("no OBS -> soft failure", path is None and isinstance(msg, str) and msg)
try:
    ObsClient(port=59999, timeout=0.5).request("GetVersion")
    check("request without connect raises ObsError", False)
except ObsError:
    check("request without connect raises ObsError", True)

# ---- watcher orchestration fails soft ---------------------------------------
guard("capture_death without OBS", lambda: dr.capture_death(
    {"kind": "death", "who": "you", "zone_at": "X", "ts": 2.0},
    [], {"obs_port": 59998}))

print(f"RESULT: {PASS} passed, {FAIL} failed")
print("ALL GREEN" if FAIL == 0 else "NOT GREEN")
sys.exit(1 if FAIL else 0)
