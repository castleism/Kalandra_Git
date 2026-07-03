"""
CORE_ENGINE/DAT_PARSER.PY
Purpose: Parse Path of Exile 2 `.datc64` data tables into structured rows, using
the community schema from poe-tool-dev/dat-schema.

This is the part of game-file extraction I can verify thoroughly (it's pure byte
parsing), so it has unit tests. The Oodle/bundle decompression that produces the
raw .datc64 files lives in ggpk_reader.py (or you use an external converter).

.datc64 layout (little-endian):
  [uint32 row_count]
  [row_count * row_width bytes]            <- fixed-width rows
  [8-byte boundary magic 0xBB*8]
  [variable-data section]                  <- strings & arrays, referenced by
                                              64-bit offsets relative to the
                                              start of this section (the magic).

Field sizes (datc64 = 64-bit references):
  bool=1, i16/u16=2, i32/u32/f32/enumrow=4, row/foreignrow(key)=8,
  string=8 (offset), array=16 (count:8 + offset:8).
Strings are UTF-16LE, null-terminated.
"""

import json
import struct

MAGIC = b"\xbb" * 8
NULL_KEY = 0xFEFEFEFEFEFEFEFE

# Byte width of a single (non-array) field of each type.
SCALAR_SIZE = {
    "bool": 1,
    "i16": 2, "u16": 2,
    "i32": 4, "u32": 4, "f32": 4, "enumrow": 4,
    "row": 8, "foreignrow": 8, "key": 8, "rid": 8,
    "string": 8,
}
# Element width when the field is an array of this type (refs become element-sized).
ELEM_SIZE = dict(SCALAR_SIZE)


def _col_size(col):
    """On-row footprint of a column (arrays are always count+offset = 16)."""
    if col.get("array"):
        return 16
    return SCALAR_SIZE.get(col["type"], 4)


def _read_string(data, data_start, rel_off):
    """Read a UTF-16LE null-terminated string at data_start+rel_off."""
    pos = data_start + rel_off
    end = pos
    n = len(data)
    while end + 1 < n:
        if data[end] == 0 and data[end + 1] == 0:
            break
        end += 2
    try:
        return data[pos:end].decode("utf-16-le", errors="replace")
    except Exception:
        return ""


def _read_scalar(data, data_start, off, typ):
    if typ == "bool":
        return data[off] != 0
    if typ in ("i16",):
        return struct.unpack_from("<h", data, off)[0]
    if typ in ("u16",):
        return struct.unpack_from("<H", data, off)[0]
    if typ in ("i32", "enumrow"):
        return struct.unpack_from("<i", data, off)[0]
    if typ == "u32":
        return struct.unpack_from("<I", data, off)[0]
    if typ == "f32":
        return struct.unpack_from("<f", data, off)[0]
    if typ in ("row", "foreignrow", "key", "rid"):
        v = struct.unpack_from("<Q", data, off)[0]
        return None if v == NULL_KEY else v
    if typ == "string":
        rel = struct.unpack_from("<Q", data, off)[0]
        return _read_string(data, data_start, rel)
    return None


def find_data_start(data):
    """Offset of the variable-data section (the boundary magic)."""
    idx = data.find(MAGIC, 4)
    return idx


def parse(data, columns):
    """Parse .datc64 `data` bytes given `columns` (list of {name,type,array}).

    Returns a list of row dicts. Unknown trailing columns are tolerated."""
    if len(data) < 4:
        return []
    row_count = struct.unpack_from("<I", data, 0)[0]
    if row_count == 0:
        return []
    data_start = find_data_start(data)
    if data_start < 0:
        raise ValueError("datc64 boundary magic not found")

    fixed_len = data_start - 4
    row_width = fixed_len // row_count
    # Sanity: the declared columns should fit within the row width.
    declared = sum(_col_size(c) for c in columns)
    if declared > row_width:
        raise ValueError(f"schema wider ({declared}) than row ({row_width}); wrong table/schema?")

    rows = []
    for r in range(row_count):
        base = 4 + r * row_width
        off = base
        row = {}
        for col in columns:
            name = col.get("name") or f"col_{off-base}"
            typ = col["type"]
            if col.get("array"):
                count = struct.unpack_from("<Q", data, off)[0]
                arr_off = struct.unpack_from("<Q", data, off + 8)[0]
                off += 16
                vals = []
                esize = ELEM_SIZE.get(typ, 4)
                p = data_start + arr_off
                for _ in range(min(count, 100000)):  # guard against corrupt counts
                    vals.append(_read_scalar(data, data_start, p, typ))
                    p += esize
                row[name] = vals
            else:
                row[name] = _read_scalar(data, data_start, off, typ)
                off += _col_size(col)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Schema helpers (poe-tool-dev/dat-schema  schema.min.json)
# ---------------------------------------------------------------------------
SCHEMA_URL = "https://github.com/poe-tool-dev/dat-schema/releases/download/latest/schema.min.json"


def load_schema(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_table_columns(schema, table_name):
    """Return the column list for a table (case-insensitive), or None."""
    tn = table_name.lower()
    for t in schema.get("tables", []):
        if t.get("name", "").lower() == tn:
            cols = []
            for c in t.get("columns", []):
                cols.append({
                    "name": c.get("name") or "",
                    "type": c.get("type", "i32"),
                    "array": bool(c.get("array")),
                    "references": c.get("references"),
                })
            return cols
    return None


if __name__ == "__main__":
    # Self-test with a synthetic 2-row table: Id(string), Level(i32), Tags(i32[]).
    cols = [{"name": "Id", "type": "string", "array": False},
            {"name": "Level", "type": "i32", "array": False},
            {"name": "Tags", "type": "i32", "array": True}]
    row_width = 8 + 4 + 16
    import struct as _s
    # variable section (after 8-byte magic at data_start):
    var = bytearray(MAGIC)
    def put(b):
        off = len(var); var.extend(b); return off
    s1 = put("Spark".encode("utf-16-le") + b"\x00\x00")
    s2 = put("Fireball".encode("utf-16-le") + b"\x00\x00")
    a1 = put(_s.pack("<ii", 10, 20))
    a2 = put(_s.pack("<i", 30))
    fixed = bytearray()
    fixed += _s.pack("<Q", s1) + _s.pack("<i", 5) + _s.pack("<QQ", 2, a1)
    fixed += _s.pack("<Q", s2) + _s.pack("<i", 92) + _s.pack("<QQ", 1, a2)
    blob = _s.pack("<I", 2) + bytes(fixed) + bytes(var)
    out = parse(blob, cols)
    print(out)
    assert out == [{"Id": "Spark", "Level": 5, "Tags": [10, 20]},
                   {"Id": "Fireball", "Level": 92, "Tags": [30]}], "parse mismatch"
    print("DAT PARSER SELF-TEST PASSED")
