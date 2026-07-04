"""
Clip-recorder pacing checks (the fix for slideshow clips).
Run: python3 tests/recorder_checks.py — pure math, no mss/cv2 needed.
"""
import os, sys, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = 0
FAIL = 0
FAILURES = []

def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL: {name}")

from core_engine.media_recorder import ScreenRecorder

plan = ScreenRecorder.plan_writes
size = ScreenRecorder.output_size

print("=== plan_writes: honest timeline via duplication ===")
FI = 1.0 / 15  # 15 fps

# On pace: one grab per slot -> one write each.
check("on pace -> 1 write", plan(0.0, FI, 0, 30) == 1)
check("slot 2 on pace", plan(FI * 1.0, FI, 1, 30) == 1)

# Slow machine: grab took 4 slots -> duplicate to catch up.
check("4 slots behind -> 4 writes", plan(FI * 4, FI, 1, 30) == 4)

# Simulated slow capture: 3 fps real vs 15 fps target over 5 seconds.
written = 0
t = 0.0
grabs = 0
while t < 5.0:
    reps = plan(t, FI, written, 30)
    written += reps
    grabs += 1
    t += 1.0 / 3          # each grab+encode takes 333ms
expect = 5.0 * 15
check("slow capture: file length ~= wall clock (±1 slot/grab)",
      abs(written - expect) <= grabs)
check("slow capture: ~5x duplication", written / grabs > 4)

# Fast machine: grabbing faster than fps must NOT overfill the file.
written = 0
t = 0.0
grabs = 0
while t < 5.0:
    reps = plan(t, FI, written, 30)
    written += reps
    grabs += 1
    # writer paces with sleep in real code; here simulate perfect pacing
    t = max(t + 0.001, written * FI)
check("fast capture: no timeline overrun (±2%)",
      abs(written - expect) <= expect * 0.02 + 1)

# Stall (system sleep 60s) capped by max_burst.
check("stall capped by max_burst", plan(60.0, FI, 10, 30) == 30)
check("never zero or negative", plan(0.0, FI, 999, 30) == 1)

print("=== output_size: downscale + even dimensions ===")
check("1080p untouched", size(1920, 1080, 1920) == (1920, 1080))
check("1440p -> 1920 wide", size(2560, 1440, 1920) == (1920, 1080))
check("4K -> 1920 wide", size(3840, 2160, 1920) == (1920, 1080))
check("odd dims forced even", size(1921, 1081, None) == (1920, 1080))
check("no cap when None", size(2560, 1440, None) == (2560, 1440))
check("ultrawide keeps aspect", size(3440, 1440, 1920)[0] == 1920
      and abs(size(3440, 1440, 1920)[1] / 1920 - 1440 / 3440) < 0.01)
check("tiny floor", size(1, 1, 1920) == (2, 2))

print("=== recorder object stays constructible headless ===")
try:
    r = ScreenRecorder(output_dir="/tmp/kal_clips", fps=15, max_width=1920)
    check("constructs", True)
    check("not recording", r.is_recording is False)
    check("stats dict present", r.last_stats == {})
    check("stop when idle is safe",
          r.stop() == {"video": None, "audio": None})
except Exception as e:
    traceback.print_exc()
    check(f"headless construction failed: {e!r}", False)

print(f"\n{'='*50}\nRESULT: {PASS} passed, {FAIL} failed")
if FAILURES:
    print("FAILURES:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("ALL GREEN")
