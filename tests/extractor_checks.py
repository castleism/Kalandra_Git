"""
TESTS/EXTRACTOR_CHECKS.PY — fixture-based checks for the game-file extraction
pipeline (core_engine/dat_parser.py, core_engine/oodle_extractor.py).

No real game files, no real Oodle DLL: everything here is a small synthetic
fixture built by hand to match the documented on-disk formats (see the module
docstrings). The one piece we can't validate without the real proprietary
oo2core DLL — the actual Oodle compression codec — is stubbed with an
identity passthrough so the surrounding format logic (bundle header framing,
index-blob layout, path-string state machine, hash auto-detection, table
lookup, byte slicing) gets exercised end to end.

Run: python3 tests/extractor_checks.py
"""
import os
import struct
import sys
import tempfile
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PASS = FAIL = 0
FAILURES = []


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL: {name}")


def guard(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
    except Exception as e:
        FAIL += 1
        FAILURES.append(f"{name}: {e!r}")
        print(f"  CRASH: {name}: {e!r}")


from core_engine import dat_parser
from core_engine.oodle_extractor import OodleExtractor

# ===========================================================================
# dat_parser: .datc64 row parsing across every scalar/array type
# ===========================================================================
print("=== dat_parser: scalar + array type coverage ===")


def build_row(fields, var_writer):
    """fields: list of (type, array, value). var_writer(bytes)->offset writes
    into the shared variable-data section and returns its relative offset."""
    out = bytearray()
    for typ, is_array, val in fields:
        if is_array:
            if typ == "string":
                offs = [var_writer(v.encode("utf-16-le") + b"\x00\x00") for v in val]
                arr_bytes = b"".join(struct.pack("<Q", o) for o in offs)
            else:
                packmap = {"i32": "<i", "u32": "<I", "row": "<Q", "foreignrow": "<Q"}
                arr_bytes = b"".join(
                    struct.pack(packmap[typ], (dat_parser.NULL_KEY if v is None else v))
                    for v in val)
            off = var_writer(arr_bytes)
            out += struct.pack("<QQ", len(val), off)
        elif typ == "bool":
            out += struct.pack("<B", 1 if val else 0)
        elif typ == "i16":
            out += struct.pack("<h", val)
        elif typ == "u16":
            out += struct.pack("<H", val)
        elif typ in ("i32", "enumrow"):
            out += struct.pack("<i", val)
        elif typ == "u32":
            out += struct.pack("<I", val)
        elif typ == "f32":
            out += struct.pack("<f", val)
        elif typ in ("row", "foreignrow", "key", "rid"):
            out += struct.pack("<Q", dat_parser.NULL_KEY if val is None else val)
        elif typ == "string":
            off = var_writer(val.encode("utf-16-le") + b"\x00\x00")
            out += struct.pack("<Q", off)
        else:
            raise ValueError(typ)
    return bytes(out)


def make_datc64(rows_fields, columns):
    """rows_fields: list of per-row field lists (type, array, value) matching
    columns. Returns the raw .datc64 bytes."""
    var = bytearray(dat_parser.MAGIC)

    def writer(b):
        off = len(var)
        var.extend(b)
        return off

    fixed = bytearray()
    for fields in rows_fields:
        fixed += build_row(fields, writer)
    return struct.pack("<I", len(rows_fields)) + bytes(fixed) + bytes(var)


columns = [
    {"name": "Id", "type": "string", "array": False},
    {"name": "Hidden", "type": "bool", "array": False},
    {"name": "MinLevel", "type": "u16", "array": False},
    {"name": "Tier", "type": "i16", "array": False},
    {"name": "Weight", "type": "f32", "array": False},
    {"name": "ParentRow", "type": "foreignrow", "array": False},
    {"name": "Tags", "type": "i32", "array": True},
    {"name": "Aliases", "type": "string", "array": True},
]
rows_fields = [
    [("string", False, "Spark"), ("bool", False, True), ("u16", False, 12),
     ("i16", False, -3), ("f32", False, 1.5), ("foreignrow", False, None),
     ("i32", True, [10, -20, 30]), ("string", True, ["Zap", "Bolt"])],
    [("string", False, "Fireball"), ("bool", False, False), ("u16", False, 65000),
     ("i16", False, 7), ("f32", False, -2.25), ("foreignrow", False, 42),
     ("i32", True, []), ("string", True, [])],
]
blob = make_datc64(rows_fields, columns)
parsed = dat_parser.parse(blob, columns)

check("parsed 2 rows", len(parsed) == 2)
check("string field", parsed[0]["Id"] == "Spark" and parsed[1]["Id"] == "Fireball")
check("bool field true/false", parsed[0]["Hidden"] is True and parsed[1]["Hidden"] is False)
check("u16 field (incl. large value)", parsed[0]["MinLevel"] == 12 and parsed[1]["MinLevel"] == 65000)
check("i16 field (negative)", parsed[0]["Tier"] == -3 and parsed[1]["Tier"] == 7)
check("f32 field (approx)", abs(parsed[0]["Weight"] - 1.5) < 1e-5
      and abs(parsed[1]["Weight"] - (-2.25)) < 1e-5)
check("foreignrow NULL_KEY -> None", parsed[0]["ParentRow"] is None)
check("foreignrow real value", parsed[1]["ParentRow"] == 42)
check("i32 array with negatives", parsed[0]["Tags"] == [10, -20, 30])
check("empty i32 array", parsed[1]["Tags"] == [])
check("string array", parsed[0]["Aliases"] == ["Zap", "Bolt"])
check("empty string array", parsed[1]["Aliases"] == [])

# row_count == 0 short-circuits
check("zero rows -> []", dat_parser.parse(struct.pack("<I", 0), columns) == [])

# missing boundary magic raises
guard_raised = False
try:
    dat_parser.parse(struct.pack("<I", 1) + b"\x00" * 8, columns)
except ValueError:
    guard_raised = True
check("missing boundary magic raises ValueError", guard_raised)

# schema wider than actual row raises (wrong table/schema guard)
narrow_row_blob = struct.pack("<I", 1) + struct.pack("<Q", 0) + dat_parser.MAGIC
wide_columns = [{"name": "A", "type": "row", "array": False},
                {"name": "B", "type": "row", "array": False}]
guard_raised = False
try:
    dat_parser.parse(narrow_row_blob, wide_columns)
except ValueError:
    guard_raised = True
check("schema wider than row raises ValueError", guard_raised)

# get_table_columns: case-insensitive lookup + miss
schema = {"tables": [{"name": "BaseItemTypes", "columns": [
    {"name": "Id", "type": "string"}, {"name": "Tags", "type": "i32", "array": True,
                                       "references": "Tags"}]}]}
cols = dat_parser.get_table_columns(schema, "baseitemtypes")
check("get_table_columns case-insensitive hit", cols is not None and len(cols) == 2)
check("get_table_columns carries references", cols[1]["references"] == "Tags")
check("get_table_columns miss -> None", dat_parser.get_table_columns(schema, "NoSuchTable") is None)

# ===========================================================================
# oodle_extractor: bundle framing + index format + path recovery + lookup,
# with the Oodle codec itself stubbed as identity (documented boundary — see
# module docstring: "the bundle/index binary format ... implemented from
# public documentation" vs the DLL call, which needs real game files).
# ===========================================================================
print("=== oodle_extractor: synthetic index + bundle round-trip ===")


def wrap_bundle(raw):
    """Frame `raw` bytes exactly as OodleExtractor._decompress_bundle expects
    a single-block .bundle.bin, for use with the identity codec stub below."""
    n = len(raw)
    header = struct.pack("<III", n, n, 0)
    header += struct.pack("<IIQQII", 0, 0, n, n, 1, max(n, 1))
    header += b"\x00" * 16
    header += struct.pack("<I", n)
    return header + raw


def identity_decompress(src, raw_size):
    return bytes(src)[:raw_size]


# -- _fnv1a64 known-vector sanity -------------------------------------------
h_empty = OodleExtractor._fnv1a64("")
check("fnv1a64 empty-string offset basis", h_empty == 0xCBF29CE484222325)
check("fnv1a64 is case-insensitive by default", OodleExtractor._fnv1a64("Data/Mods.datc64")
      == OodleExtractor._fnv1a64("data/mods.datc64"))

# -- _make_paths: base-string + fragment state machine ----------------------
def encode_frag(base):
    def frag(idx, s):
        b = struct.pack("<I", idx)
        if idx != 0:
            b += s.encode("utf-8") + b"\x00"
        return b
    return frag


frag = encode_frag(True)
dir_data = bytearray()
dir_data += frag(0, "")                 # toggle base=True
dir_data += frag(1, "data/")            # temp[0] = "data/"
dir_data += frag(0, "")                 # toggle base=False
dir_data += frag(1, "baseitemtypes.datc64")   # res += temp[0]+frag
dir_data += frag(1, "mods.datc64")            # res += temp[0]+frag
dir_data = bytes(dir_data)

paths = OodleExtractor._make_paths(dir_data, 0, len(dir_data))
check("path recovery: base+fragment reconstruction", paths ==
      ["data/baseitemtypes.datc64", "data/mods.datc64"])

# -- full synthetic index + bundle round trip via a temp "install" ----------
tmpdir = tempfile.mkdtemp(prefix="kalandra_extractor_test_")
try:
    bundles_dir = os.path.join(tmpdir, "Bundles2")
    os.makedirs(bundles_dir, exist_ok=True)

    base_content = b"BASEITEMTYPESDATA123"
    mods_content = b"MODSDATA456"
    combined = base_content + mods_content
    with open(os.path.join(bundles_dir, "test.bundle.bin"), "wb") as f:
        f.write(wrap_bundle(combined))

    path_a, path_b = "data/baseitemtypes.datc64", "data/mods.datc64"
    h_a = OodleExtractor._fnv1a64(path_a)
    h_b = OodleExtractor._fnv1a64(path_b)

    index_blob = bytearray()
    index_blob += struct.pack("<I", 1)                      # bundle_count
    name = b"test"
    index_blob += struct.pack("<I", len(name)) + name + struct.pack("<I", 0)
    index_blob += struct.pack("<I", 2)                       # file_count
    index_blob += struct.pack("<QIII", h_a, 0, 0, len(base_content))
    index_blob += struct.pack("<QIII", h_b, 0, len(base_content), len(mods_content))
    index_blob += struct.pack("<I", 1)                       # dir_count
    index_blob += struct.pack("<QIII", 0, 0, len(dir_data), 0)
    index_blob += wrap_bundle(dir_data)                       # path_rep

    with open(os.path.join(bundles_dir, "_.index.bin"), "wb") as f:
        f.write(wrap_bundle(bytes(index_blob)))

    ex = OodleExtractor(install_dir=tmpdir)
    ex._oodle_decompress = identity_decompress   # stub the DLL-only codec

    stats = ex.build_index()
    check("build_index: ok", stats.get("ok") is True)
    check("build_index: matched both synthetic files", stats.get("matched") == 2)
    check("build_index: recovered both paths", stats.get("paths") == 2)

    tp = ex.find_table_path("BaseItemTypes")
    check("find_table_path resolves case-insensitively", tp == path_a)
    check("find_table_path miss -> None", ex.find_table_path("NoSuchTable") is None)

    check("extract_file: exact byte slice (base)", ex.extract_file(path_a) == base_content)
    check("extract_file: exact byte slice (mods)", ex.extract_file(path_b) == mods_content)

    out_dir = os.path.join(tmpdir, "out")
    result = ex.extract_tables(["BaseItemTypes", "Mods", "Missing"], out_dir)
    check("extract_tables: writes recognized tables", set(result["written"]) == {"BaseItemTypes", "Mods"})
    check("extract_tables: reports unrecognized as missing", result["missing"] == ["Missing"])
    with open(os.path.join(out_dir, "data", "BaseItemTypes.datc64"), "rb") as f:
        check("extract_tables: on-disk bytes match", f.read() == base_content)
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# -- self_test degrades gracefully with no install / no DLL -----------------
# Force the "not found" branch directly (rather than relying on find_install
# failing) so this stays deterministic on a machine that DOES have a real
# PoE2 install under one of the default candidate paths.
ex2 = OodleExtractor(install_dir=None)
ex2.install = None
guard("self_test on missing install doesn't crash", ex2.self_test)
rep = ex2.self_test()
check("self_test reports install missing", rep["install"] is False and rep["notes"])

# ===========================================================================
# poe2_data_extract: in-process extraction wiring (PoE2DataExtractor <->
# OodleExtractor), independent of whether THIS machine has a real install.
# ===========================================================================
print("=== poe2_data_extract: in-process extraction wiring ===")

from core_engine import poe2_data_extract as p2de


class FakeDB:
    def __init__(self):
        self.rows = []

    def insert_scoured_data(self, topic, content, url, version):
        self.rows.append((topic, content, url, version))


tmp2 = tempfile.mkdtemp(prefix="kalandra_p2de_test_")
try:
    orig_cwd = os.getcwd()
    os.chdir(tmp2)

    db = FakeDB()
    px = p2de.PoE2DataExtractor(db_handler=db)

    # -- not ready: no install, no DLL --------------------------------------
    class NotReadyExtractor:
        def __init__(self, logger=None):
            pass

        def status(self):
            return {"install": None, "oo2core_dll": None, "index_bin": None, "ready": False}

    orig_cls = p2de.OodleExtractor
    p2de.OodleExtractor = NotReadyExtractor
    try:
        result = px.extract_in_process(tables=["BaseItemTypes"])
        check("extract_in_process: not-ready reports empty written", result["written"] == [])
        check("extract_in_process: not-ready carries all tables as missing",
              result["missing"] == ["BaseItemTypes"])
        check("extract_in_process: not-ready gives a reason", "reason" in result)

        s = px.scan()
        check("scan(): surfaces in_process status", s["in_process"]["ready"] is False)

        au = px.auto_update()
        check("auto_update(): no-data when nothing extracted and not ready",
              au["status"] == "no-data")
    finally:
        p2de.OodleExtractor = orig_cls

    # -- ready: fake extractor "writes" tables by dropping fixture datc64 --
    class ReadyExtractor:
        def __init__(self, logger=None):
            self.logger = logger

        def status(self):
            return {"install": "/fake/install", "oo2core_dll": "/fake/oo2core.dll",
                     "index_bin": "/fake/_.index.bin", "ready": True}

        def extract_tables(self, tables, out_dir):
            os.makedirs(os.path.join(out_dir, "data"), exist_ok=True)
            written = []
            for t in tables:
                with open(os.path.join(out_dir, "data", t + ".datc64"), "wb") as f:
                    f.write(make_datc64(
                        [[("string", False, f"{t}Row0")]],
                        [{"name": "Id", "type": "string", "array": False}]))
                written.append(t)
            return {"written": written, "missing": []}

    # a minimal local schema so import_datc64_dir doesn't need network access
    os.makedirs("data_engine", exist_ok=True)
    fake_schema = {"tables": [
        {"name": "BaseItemTypes", "columns": [{"name": "Id", "type": "string"}]},
        {"name": "Mods", "columns": [{"name": "Id", "type": "string"}]},
    ]}
    with open(p2de.SCHEMA_PATH, "w", encoding="utf-8") as f:
        import json as _json
        _json.dump(fake_schema, f)

    p2de.OodleExtractor = ReadyExtractor
    try:
        result = px.extract_in_process(tables=["BaseItemTypes", "Mods"])
        check("extract_in_process: ready writes requested tables",
              set(result["written"]) == {"BaseItemTypes", "Mods"})

        s = px.scan()
        check("scan(): sees the in-process-extracted files", s["extracted_files"] == 2)

        au = px.auto_update()
        check("auto_update(): self-extracts then imports when ready",
              au["status"] == "imported" and au["rows"] == 2)
        check("auto_update(): rows actually landed in the db",
              len(db.rows) == 2 and any("BaseItemTypesRow0" in c for _, c, _, _ in db.rows))
    finally:
        p2de.OodleExtractor = orig_cls
finally:
    os.chdir(orig_cwd)
    shutil.rmtree(tmp2, ignore_errors=True)

print(f"\n{'='*50}\nRESULT: {PASS} passed, {FAIL} failed")
if FAILURES:
    print("FAILURES:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("ALL GREEN")
