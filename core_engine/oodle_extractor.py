"""
CORE_ENGINE/OODLE_EXTRACTOR.PY
In-process extraction of PoE2 game data: decompress the game's Oodle bundles
using the game's OWN oo2core DLL (via ctypes) -- nothing is redistributed.

STATUS: EXPERIMENTAL. The bundle/index binary format and Oodle calling
convention are implemented from public documentation, but I can't validate this
without the real game files + DLL on a Windows machine. The `self_test()` method
reports exactly which steps work so it can be fixed iteratively. Until it passes,
use the external-converter route (EXTRACTOR_SETUP.md).

Design:
  * locate the install + oo2core_*.dll
  * OodleLZ_Decompress via ctypes
  * read Bundles2/_.index.bin (itself a bundle), recover file paths
  * decompress the bundles holding the .datc64 tables we want
"""

import os
import glob
import struct
import ctypes

OO2CORE_GLOBS = ["oo2core_*.dll", "oo2core_*win64.dll"]
INSTALL_CANDIDATES = [
    r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile 2",
    r"C:\Program Files\Grinding Gear Games\Path of Exile 2",
    r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile 2",
    r"C:\Program Files\Steam\steamapps\common\Path of Exile 2",
    r"D:\Steam\steamapps\common\Path of Exile 2",
    r"D:\SteamLibrary\steamapps\common\Path of Exile 2",
    r"E:\SteamLibrary\steamapps\common\Path of Exile 2",
]


def find_install(explicit=None):
    cands = ([explicit] if explicit else []) + INSTALL_CANDIDATES
    for d in cands:
        if d and os.path.isdir(d) and (
                os.path.isdir(os.path.join(d, "Bundles2"))
                or os.path.exists(os.path.join(d, "Content.ggpk"))):
            return d
    return None


DLL_PATTERNS = ("oo2core*.dll", "oodle*.dll", "*oo2*.dll")


def _dll_search_roots(install, extra=None):
    """Everywhere worth looking for the game's Oodle DLL."""
    roots = []
    if install:
        roots.append(install)
        roots.append(os.path.dirname(install))   # parent (install may be a subfolder)
    for e in (extra or []):
        if e:
            roots.append(e)
    # de-dup, keep order
    seen, out = set(), []
    for r in roots:
        if r and r not in seen and os.path.isdir(r):
            seen.add(r); out.append(r)
    return out


def _configured_oo2core():
    """An explicit oo2core DLL the user pointed us at (data_engine/config.json)."""
    try:
        import json
        with open(os.path.join("data_engine", "config.json"), "r", encoding="utf-8") as f:
            p = json.load(f).get("oo2core_dll")
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    return None


def _steam_sibling_dlls(install):
    """Oodle (oo2core_*.dll) ships with MANY games. If PoE2 is a Steam install,
    shallow-scan the other games under steamapps/common for a compatible DLL."""
    if not install:
        return None
    low = install.replace("\\", "/").lower()
    idx = low.find("steamapps/common")
    if idx < 0:
        return None
    common = install[:idx] + install[idx:idx + len("steamapps/common")]
    for depth in ("*", os.path.join("*", "*")):
        for pat in DLL_PATTERNS:
            hits = glob.glob(os.path.join(common, depth, pat))
            if hits:
                return hits[0]
    return None


def find_oo2core(install, extra_roots=None, explicit=None):
    """Locate an Oodle DLL. Order: user-set DLL -> the game's own folder ->
    recursive -> a sibling Steam game that ships oo2core."""
    explicit = explicit or _configured_oo2core()
    if explicit and os.path.isfile(explicit):
        return explicit
    for root in _dll_search_roots(install, extra_roots):
        for pat in DLL_PATTERNS:
            hits = glob.glob(os.path.join(root, pat))
            if hits:
                return hits[0]
    for root in _dll_search_roots(install, extra_roots):
        for pat in DLL_PATTERNS:
            hits = glob.glob(os.path.join(root, "**", pat), recursive=True)
            if hits:
                return hits[0]
    return _steam_sibling_dlls(install)


def list_root_dlls(install, limit=40):
    """Diagnostic: what .dll files actually sit at the install root (and parent)?"""
    names = []
    for root in _dll_search_roots(install):
        try:
            for fn in sorted(os.listdir(root)):
                if fn.lower().endswith(".dll") and fn not in names:
                    names.append(fn)
        except Exception:
            pass
        if len(names) >= limit:
            break
    return names[:limit]


class OodleExtractor:
    def __init__(self, install_dir=None, logger=None):
        self.install = find_install(install_dir)
        self.dll_path = find_oo2core(self.install)
        self.logger = logger
        self._oodle = None

    def _log(self, msg):
        if self.logger:
            try:
                self.logger("DATABASE", msg)
            except Exception:
                pass

    # -- Oodle DLL ------------------------------------------------------------
    def _load_oodle(self):
        if self._oodle is not None:
            return self._oodle
        if not self.dll_path:
            return None
        try:
            lib = ctypes.CDLL(self.dll_path)
            fn = lib.OodleLZ_Decompress
            fn.restype = ctypes.c_int64
            fn.argtypes = [
                ctypes.c_void_p, ctypes.c_int64,   # src, srcLen
                ctypes.c_void_p, ctypes.c_int64,   # dst, dstLen
                ctypes.c_int32, ctypes.c_int32, ctypes.c_int64,  # fuzz, crc, verbose
                ctypes.c_void_p, ctypes.c_int64,   # decBufBase, decBufSize
                ctypes.c_void_p, ctypes.c_void_p,  # cb, cbctx
                ctypes.c_void_p, ctypes.c_int64,   # scratch, scratchSize
                ctypes.c_int32,                    # threadPhase
            ]
            self._oodle = (lib, fn)
            return self._oodle
        except Exception as e:
            self._log(f"Could not load Oodle DLL: {e}")
            return None

    def _oodle_decompress(self, src, raw_size):
        o = self._load_oodle()
        if not o:
            return None
        _, fn = o
        dst = ctypes.create_string_buffer(raw_size + 64)
        srcbuf = ctypes.create_string_buffer(bytes(src), len(src))
        n = fn(ctypes.cast(srcbuf, ctypes.c_void_p), len(src),
               ctypes.cast(dst, ctypes.c_void_p), raw_size,
               1, 0, 0, None, 0, None, None, None, 0, 3)
        if n <= 0:
            return None
        return dst.raw[:raw_size]

    # -- bundle format --------------------------------------------------------
    def _decompress_bundle(self, data):
        """Decompress a whole .bundle.bin (header + Oodle blocks)."""
        try:
            (uncompressed_size, total_payload, head_size) = struct.unpack_from("<III", data, 0)
            off = 12
            (first_encode, unk, uncompressed_size64, total_payload64,
             block_count, granularity) = struct.unpack_from("<IIQQII", data, off)
            off += 4 + 4 + 8 + 8 + 4 + 4
            off += 4 * 4  # 4 unused uint32
            block_sizes = list(struct.unpack_from("<%dI" % block_count, data, off))
            off += 4 * block_count
            out = bytearray()
            remaining = uncompressed_size64
            for i, bsize in enumerate(block_sizes):
                raw = granularity if remaining > granularity else remaining
                chunk = self._oodle_decompress(data[off:off + bsize], raw)
                if chunk is None:
                    return None
                out += chunk
                off += bsize
                remaining -= raw
            return bytes(out)
        except Exception as e:
            self._log(f"Bundle decode failed: {e}")
            return None

    def index_bin_path(self):
        if not self.install:
            return None
        p = os.path.join(self.install, "Bundles2", "_.index.bin")
        return p if os.path.exists(p) else None

    # -- index: file path recovery -------------------------------------------
    @staticmethod
    def _fnv1a64(s, lower=True):
        """FNV-1a 64-bit (the hash PoE/PoE2 uses for bundled file paths)."""
        data = (s.lower() if lower else s).encode("utf-8")
        h = 0xCBF29CE484222325
        for b in data:
            h = ((h ^ b) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
        return h

    @staticmethod
    def _hash_candidates():
        """All path-hash functions to try, by name. PoE has used both FNV-1a-64
        and MurmurHash64A across versions, over the path in various forms; we
        auto-detect which one this game build uses."""
        MASK = 0xFFFFFFFFFFFFFFFF

        def fnv(data):
            h = 0xCBF29CE484222325
            for b in data:
                h = ((h ^ b) * 0x100000001B3) & MASK
            return h

        def murmur(data, seed=0):
            m = 0xC6A4A7935BD1E995
            r = 47
            L = len(data)
            h = (seed ^ ((L * m) & MASK)) & MASK
            n = L // 8
            for i in range(n):
                k = struct.unpack_from("<Q", data, i * 8)[0]
                k = (k * m) & MASK
                k ^= k >> r
                k = (k * m) & MASK
                h ^= k
                h = (h * m) & MASK
            tail = data[n * 8:]
            for i in range(len(tail) - 1, -1, -1):
                h = (h ^ (tail[i] << (8 * i))) & MASK
            if tail:
                h = (h * m) & MASK
            h ^= h >> r
            h = (h * m) & MASK
            h ^= h >> r
            return h & MASK

        u8 = lambda p: p.encode("utf-8")
        u8l = lambda p: p.lower().encode("utf-8")
        u8u = lambda p: p.upper().encode("utf-8")
        u8lb = lambda p: p.lower().replace("/", "\\").encode("utf-8")
        u16l = lambda p: p.lower().encode("utf-16-le")
        S = 0x1337B33F            # a seed PoE has used in places
        return {
            "fnv_lower": lambda p: fnv(u8l(p)),
            "fnv_asis": lambda p: fnv(u8(p)),
            "fnv_upper": lambda p: fnv(u8u(p)),
            "fnv_lower_nul": lambda p: fnv(u8l(p) + b"\x00"),
            "fnv_lower_bslash": lambda p: fnv(u8lb(p)),
            "fnv_lower_utf16": lambda p: fnv(u16l(p)),
            "fnv_lower_slashpfx": lambda p: fnv(b"/" + u8l(p)),
            "murmur_lower": lambda p: murmur(u8l(p)),
            "murmur_asis": lambda p: murmur(u8(p)),
            "murmur_lower_bslash": lambda p: murmur(u8lb(p)),
            "murmur_lower_nul": lambda p: murmur(u8l(p) + b"\x00"),
            "murmur_lower_utf16": lambda p: murmur(u16l(p)),
            "murmur_lower_s1337": lambda p: murmur(u8l(p), S),
            "murmur_asis_s1337": lambda p: murmur(u8(p), S),
        }

    @staticmethod
    def _make_paths(data, start, size):
        """Rebuild full file paths from a directory slice of the path-rep bundle.
        Mirrors the reference 'base string' state machine used by LibGGPK/ooz."""
        res = []
        temp = []
        base = False
        off = start
        end = min(start + size, len(data))
        while off + 4 <= end:
            idx = struct.unpack_from("<I", data, off)[0]
            off += 4
            if idx == 0:
                base = not base
                if base:
                    temp = []
                continue
            idx -= 1
            s_start = off
            while off < len(data) and data[off] != 0:
                off += 1
            frag = data[s_start:off].decode("utf-8", "replace")
            off += 1  # skip null terminator
            full = (temp[idx] + frag) if idx < len(temp) else frag
            if base:
                temp.append(full)
            else:
                res.append(full)
        return res

    def _read_bundle_by_name(self, name):
        """Read + decompress a physical Bundles2/<name>.bundle.bin (cached)."""
        cache = self.__dict__.setdefault("_bundle_cache", {})
        if name in cache:
            return cache[name]
        rel = name.split("/")
        path = os.path.join(self.install, "Bundles2", *rel) + ".bundle.bin"
        if not os.path.exists(path):
            cache[name] = None
            return None
        try:
            with open(path, "rb") as f:
                raw = f.read()
            data = self._decompress_bundle(raw)
        except Exception as e:
            self._log(f"Bundle read failed ({name}): {e}")
            data = None
        cache[name] = data
        return data

    def build_index(self):
        """Decompress _.index.bin, recover every file's (bundle, offset, size)
        keyed by lowercase path. Cached on the instance. Returns a stats dict."""
        if getattr(self, "_index_stats", None) is not None:
            return self._index_stats
        stats = {"ok": False, "files": 0, "paths": 0, "matched": 0, "strategy": None}
        ip = self.index_bin_path()
        if not ip:
            return stats
        try:
            with open(ip, "rb") as f:
                blob = self._decompress_bundle(f.read())
            if not blob:
                return stats
            off = 0
            bundle_count = struct.unpack_from("<I", blob, off)[0]; off += 4
            bundles = []
            for _ in range(bundle_count):
                nlen = struct.unpack_from("<I", blob, off)[0]; off += 4
                name = blob[off:off + nlen].decode("utf-8", "replace"); off += nlen
                off += 4  # uncompressed size (unused)
                bundles.append(name)
            file_count = struct.unpack_from("<I", blob, off)[0]; off += 4
            files = []
            for _ in range(file_count):
                h, bidx, foff, fsize = struct.unpack_from("<QIII", blob, off)
                off += 20
                files.append((h, bidx, foff, fsize))
            dir_count = struct.unpack_from("<I", blob, off)[0]; off += 4
            dirs = []
            for _ in range(dir_count):
                dh, doff, dsize, drec = struct.unpack_from("<QIII", blob, off)
                off += 20
                dirs.append((doff, dsize))
            path_rep = blob[off:]
            path_data = self._decompress_bundle(path_rep)
            paths = []
            if path_data:
                for (doff, dsize) in dirs:
                    paths.extend(self._make_paths(path_data, doff, dsize))

            files_by_hash = {h: (bidx, foff, fsize) for (h, bidx, foff, fsize) in files}

            # Auto-detect the hash function on a SAMPLE (fast), then apply the
            # winner to every path. PoE has changed hashing between versions, so
            # we score many candidates and keep whichever actually matches.
            candidates = self._hash_candidates()
            step = max(1, len(paths) // 4000)
            sample = paths[::step][:4000]
            scores = {}
            for name, fn in candidates.items():
                hit = 0
                for p in sample:
                    try:
                        if fn(p) in files_by_hash:
                            hit += 1
                    except Exception:
                        break
                scores[name] = hit
            best_name = max(scores, key=scores.get) if scores else None
            sample_rate = (scores.get(best_name, 0) / len(sample)) if sample else 0

            best_map = {}
            if best_name and sample_rate >= 0.10:
                fn = candidates[best_name]
                for p in paths:
                    e = files_by_hash.get(fn(p))
                    if e:
                        best_map[p.lower()] = e

            self._bundles = bundles
            self._file_map = best_map
            self._dbg = {"records": blob, "pathrep_compressed": path_rep,
                         "pathdata": path_data, "files": files, "dirs": dirs,
                         "bundles": bundles, "paths": paths}
            stats.update(ok=bool(best_map), files=file_count, paths=len(paths),
                         matched=len(best_map), strategy=best_name, bundles=bundle_count,
                         hash_scores={k: f"{v}/{len(sample)}" for k, v in
                                      sorted(scores.items(), key=lambda kv: -kv[1])})
        except Exception as e:
            self._log(f"Index parse failed: {e}")
            stats["error"] = str(e)
        self._index_stats = stats
        return stats

    def dump_debug(self, out_dir):
        """Write the decompressed index + path strings + a JSON summary to disk so
        the real on-disk layout can be inspected when path recovery fails."""
        import json
        self.build_index()
        d = getattr(self, "_dbg", None)
        if not d:
            return None
        try:
            os.makedirs(out_dir, exist_ok=True)
            with open(os.path.join(out_dir, "_debug_records.bin"), "wb") as f:
                f.write(d.get("records") or b"")
            with open(os.path.join(out_dir, "_debug_pathdata.bin"), "wb") as f:
                f.write(d.get("pathdata") or b"")
            summary = {
                "bundle_count": len(d["bundles"]),
                "bundles_sample": d["bundles"][:25],
                "file_count": len(d["files"]),
                "files_sample": [{"hash": "%016x" % h, "bundle": b, "off": o, "size": s}
                                 for (h, b, o, s) in d["files"][:40]],
                "dir_count": len(d["dirs"]),
                "dirs_sample": d["dirs"][:40],
                "records_len": len(d.get("records") or b""),
                "pathdata_len": len(d.get("pathdata") or b""),
                "pathrep_compressed_len": len(d.get("pathrep_compressed") or b""),
                "paths_recovered": len(d["paths"]),
                "paths_sample": d["paths"][:60],
            }
            with open(os.path.join(out_dir, "_debug_index.json"), "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=1)
            self._log(f"Wrote index debug files to {out_dir} (_debug_records.bin, "
                      f"_debug_pathdata.bin, _debug_index.json).")
            return out_dir
        except Exception as e:
            self._log(f"Debug dump failed: {e}")
            return None

    def find_table_path(self, table):
        """Locate a .datc64 table in the recovered file list (case-insensitive)."""
        fm = getattr(self, "_file_map", None)
        if not fm:
            return None
        needle = (table + ".datc64").lower()
        for key in fm:
            if key.endswith("/" + needle) or key == needle:
                return key
        for key in fm:                       # looser fallback
            if key.endswith(needle):
                return key
        return None

    def extract_file(self, path):
        """Return the raw bytes of one recovered file path, or None."""
        fm = getattr(self, "_file_map", None)
        if not fm:
            return None
        entry = fm.get(path.lower())
        if not entry:
            return None
        bidx, foff, fsize = entry
        bundle = self._read_bundle_by_name(self._bundles[bidx])
        if not bundle:
            return None
        return bundle[foff:foff + fsize]

    def extract_tables(self, tables, out_dir):
        """Extract the named .datc64 tables to out_dir/data/<Table>.datc64.
        Returns {"written": [...], "missing": [...]}."""
        self.build_index()
        os.makedirs(os.path.join(out_dir, "data"), exist_ok=True)
        written, missing = [], []
        for t in tables:
            key = self.find_table_path(t)
            data = self.extract_file(key) if key else None
            if data:
                dest = os.path.join(out_dir, "data", t + ".datc64")
                try:
                    with open(dest, "wb") as f:
                        f.write(data)
                    written.append(t)
                except Exception as e:
                    self._log(f"Could not write {t}: {e}")
                    missing.append(t)
            else:
                missing.append(t)
        self._log(f"Game-data extraction: wrote {len(written)} tables "
                  f"({', '.join(written) or 'none'}); missing: {', '.join(missing) or 'none'}.")
        return {"written": written, "missing": missing}

    # -- diagnostics ----------------------------------------------------------
    def status(self):
        return {
            "install": self.install,
            "oo2core_dll": self.dll_path,
            "index_bin": self.index_bin_path(),
            "ready": bool(self.install and self.dll_path and self.index_bin_path()),
        }

    def self_test(self):
        """Step-by-step probe so failures are diagnosable. Returns a report dict."""
        rep = {"install": bool(self.install), "dll": bool(self.dll_path),
               "index": bool(self.index_bin_path()), "dll_loaded": False,
               "index_decompressed": False,
               "install_path": self.install or "(none)", "notes": []}
        if not self.install:
            rep["notes"].append("PoE2 install not found. Set \"game_install_dir\" in "
                                "data_engine/config.json to your Path of Exile 2 folder.")
            return rep
        if not self.dll_path:
            # Tell us what IS at the install root so we can target the real DLL.
            dlls = list_root_dlls(self.install)
            rep["dlls_seen"] = dlls
            shown = ", ".join(dlls) if dlls else "none"
            rep["notes"].append(
                f"Oodle DLL not found under: {self.install}")
            rep["notes"].append(f".dll files at that location: {shown}")
            rep["notes"].append(
                "No Oodle DLL here. FIX 1 (best): in Steam, Path of Exile 2 -> "
                "Properties -> Installed Files -> 'Verify integrity of game files' "
                "(this restores a missing oo2core). FIX 2: point Kalandra at any "
                "compatible oo2core_*.dll you already have (it ships with many games) "
                "by setting \"oo2core_dll\" in data_engine/config.json to that file. "
                "I auto-scan your other Steam games for one too.")
            return rep
        if not self._load_oodle():
            rep["notes"].append("Oodle DLL present but failed to load via ctypes "
                                "(architecture mismatch? use 64-bit Python).")
            return rep
        rep["dll_loaded"] = True
        ip = self.index_bin_path()
        if not ip:
            rep["notes"].append("Bundles2/_.index.bin not found (Steam loose format?).")
            return rep
        try:
            with open(ip, "rb") as f:
                data = f.read()
            out = self._decompress_bundle(data)
            if out:
                rep["index_decompressed"] = True
                rep["index_size"] = len(out)
                # Go one step further: recover file paths and locate our tables.
                ix = self.build_index()
                rep["paths_recovered"] = ix.get("paths", 0)
                rep["files_matched"] = ix.get("matched", 0)
                rep["hash_strategy"] = ix.get("strategy")
                if ix.get("ok"):
                    found = [t for t in ("BaseItemTypes", "Mods", "SkillGems", "Stats")
                             if self.find_table_path(t)]
                    rep["sample_tables_found"] = found
                    rep["notes"].append(
                        f"Path recovery OK: {ix['matched']:,}/{ix['files']:,} files "
                        f"matched ({ix['strategy']}). Sample tables located: "
                        f"{', '.join(found) or 'none'}. Ready to extract — click "
                        f"'Extract game data now'.")
                else:
                    rep["notes"].append(
                        f"Index decompressed but path recovery failed: "
                        f"{ix.get('paths',0):,} path strings recovered, "
                        f"{ix.get('files',0):,} file records, 0 hash matches.")
                    if ix.get("hash_scores"):
                        rep["notes"].append("Hash candidate scores (sampled): "
                                            + ", ".join(f"{k}={v}" for k, v in
                                                        ix["hash_scores"].items()))
            else:
                rep["notes"].append("Index bundle did not decompress — the bundle header "
                                    "layout likely needs adjusting for this game build.")
        except Exception as e:
            rep["notes"].append(f"Index read error: {e}")
        return rep


if __name__ == "__main__":
    ex = OodleExtractor(logger=lambda c, m: print(f"[{c}] {m}"))
    import pprint
    pprint.pprint(ex.status())
    pprint.pprint(ex.self_test())
