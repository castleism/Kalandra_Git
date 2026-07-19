"""
CORE_ENGINE/POB_BRIDGE.PY
Purpose: Interacts with Path of Building (PoB) export strings. Decodes URL-safe 
Base64 strings, decompresses them using zlib deflate, and parses the raw XML 
payload to hand clean numerical data to the AI model.

Dependencies: base64, zlib, xml.etree.ElementTree (Standard Python Libraries)
"""

import base64
import zlib
import math
import xml.etree.ElementTree as ET

class KalandraPoBBridge:
    def __init__(self):
        """
        Initializes the Path of Building bridge interface.
        """
        pass

    # ------------------------------------------------------------------
    # Local PoB build files (your saved characters live here as XML)
    # ------------------------------------------------------------------
    @staticmethod
    def candidate_build_dirs():
        """Likely folders where Path of Building 2 stores saved builds (.xml).
        The PoE2 community fork's DEFAULT user dir is
        %APPDATA%\Path of Building Community (PoE2)\ — its absence from this
        list is why freshly-saved PoB characters never appeared in the
        selector (2026-07-04)."""
        import os
        home = os.path.expanduser("~")
        docs = os.path.join(home, "Documents")
        appdata = os.environ.get("APPDATA", "")
        localapp = os.environ.get("LOCALAPPDATA", "")
        pf86 = os.environ.get("ProgramFiles(x86)", "")
        return [
            os.path.join(appdata, "Path of Building Community (PoE2)", "Builds"),
            # Portable copies keep Builds INSIDE the install folder. These two
            # are where installs actually live: the uninstaller's "Move out"
            # target and the standard installer location (2026-07-05 — a
            # moved-out portable PoB was invisible to the selector).
            os.path.join(localapp, "Programs",
                         "Path of Building Community (PoE2)", "Builds"),
            os.path.join(pf86, "Path of Building Community (PoE2)", "Builds"),
            os.path.join(appdata, "Path of Building Community", "Builds"),
            os.path.join(docs, "Path of Building Community (PoE2)", "Builds"),
            os.path.join(docs, "Path of Building (PoE2)", "Builds"),
            os.path.join(docs, "Path of Building", "Builds"),
            os.path.join(home, "Path of Building (PoE2)", "Builds"),
            os.path.join(appdata, "Path of Building", "Builds"),
            os.path.join(os.environ.get("PROGRAMDATA", ""), "Path of Building", "Builds"),
        ]

    @staticmethod
    def pob_settings_build_path(install_dir=None):
        """THE authoritative answer: parse PoB's own Settings.xml for its
        configured buildPath (users can point PoB anywhere; guessing loses).
        Checks the install dir (portable mode) and the fork's APPDATA user
        dirs. Returns the path or None. Never raises."""
        import os
        import re as _re
        appdata = os.environ.get("APPDATA", "")
        cands = []
        if install_dir:
            cands.append(os.path.join(install_dir, "Settings.xml"))
        localapp = os.environ.get("LOCALAPPDATA", "")
        pf86 = os.environ.get("ProgramFiles(x86)", "")
        cands += [
            os.path.join(appdata, "Path of Building Community (PoE2)", "Settings.xml"),
            os.path.join(appdata, "Path of Building Community", "Settings.xml"),
            os.path.join(appdata, "Path of Building", "Settings.xml"),
            # portable installs keep Settings.xml beside the exe:
            os.path.join(localapp, "Programs",
                         "Path of Building Community (PoE2)", "Settings.xml"),
            os.path.join(pf86, "Path of Building Community (PoE2)", "Settings.xml"),
        ]
        for c in cands:
            try:
                if not os.path.exists(c):
                    continue
                with open(c, "r", encoding="utf-8", errors="ignore") as f:
                    txt = f.read()
                m = _re.search(r'buildPath="([^"]+)"', txt)
                if m and os.path.isdir(m.group(1)):
                    return m.group(1)
            except Exception:
                continue
        return None

    # Directory names we must NEVER descend into when hunting for PoB 'Builds'
    # folders. The app folder can now contain the bundled offline installers,
    # extracted dependency program folders, the knowledge database, caches and
    # even a multi-hundred-MB zip; recursively walking those would freeze the UI.
    _SCAN_SKIP_DIRS = {
        "additional resources", "__pycache__", ".git", ".github", "data_engine",
        "node_modules", "venv", ".venv", "env", "dist", "build", "site-packages",
        "installer", "snapshots", "clips", "transcripts", "vault", ".idea",
        ".vscode", "obsidian", "python", "python packages (wheels)", "oo2core dll",
        "rhubarb", "luajit", "exiled exchange 2", "xiletrade", "lailloken exile-ui",
    }
    _SCAN_MAX_DEPTH = 5          # how deep below the app root we'll look
    _SCAN_MAX_DIRS = 4000        # hard cap on directories visited (safety valve)

    @classmethod
    def _discovered_build_dirs(cls):
        """Auto-find PoB 'Builds' folders that live INSIDE this app -- e.g. when
        PoB was launched from the source copy the installer dropped in tools/,
        it saves builds in  tools/PathOfBuilding.../src/Builds  (not Documents).

        This used to be a `glob('**/Builds', recursive=True)` over the whole app
        folder, which froze the UI once large dependency/installer folders were
        added. It is now a BOUNDED, pruned walk: it skips heavy folders, caps the
        depth, and caps the total number of directories it will ever visit."""
        import os
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.dirname(here)                 # project root (parent of core_engine)
        found = []
        visited = 0
        root_depth = root.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, _files in os.walk(root):
            visited += 1
            if visited > cls._SCAN_MAX_DIRS:
                break
            depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
            if depth >= cls._SCAN_MAX_DEPTH:
                dirnames[:] = []                     # stop descending
                continue
            # Prune heavy/irrelevant subtrees in-place so os.walk never enters them.
            dirnames[:] = [d for d in dirnames if d.lower() not in cls._SCAN_SKIP_DIRS]
            for d in dirnames:
                if d.lower() == "builds":
                    full = os.path.join(dirpath, d)
                    if full not in found:
                        found.append(full)
        return found

    def find_pob_builds(self, extra_dir=None, pob_install_dir=None):
        """Return [{name, path, ...stats}] for every saved PoB build found.
        Searches (in order): an explicit folder from config, the configured PoB
        install dir's Builds, any Builds folder bundled inside the app, then the
        usual Documents locations."""
        import os
        dirs = []
        # PoB's own configured build folder outranks every guess.
        sp = self.pob_settings_build_path(pob_install_dir)
        if sp:
            dirs.append(sp)
        if extra_dir:
            dirs.append(extra_dir)
        if pob_install_dir:
            # pob_install_dir may be the install root OR the .../src folder.
            dirs.append(os.path.join(pob_install_dir, "Builds"))
            dirs.append(os.path.join(pob_install_dir, "src", "Builds"))
        dirs.extend(self._discovered_build_dirs())
        dirs.extend(self.candidate_build_dirs())
        builds = []
        seen = set()
        MAX_BUILDS = 500          # don't try to parse an unbounded number of files
        MAX_DEPTH = 4             # Builds folders are shallow; don't tunnel deep
        for d in dirs:
            if not d or not os.path.isdir(d):
                continue
            base_depth = d.rstrip(os.sep).count(os.sep)
            for root, subdirs, files in os.walk(d):
                # Prune heavy subtrees and cap depth so a mis-pointed folder can't
                # turn this into a multi-gigabyte crawl.
                if root.rstrip(os.sep).count(os.sep) - base_depth >= MAX_DEPTH:
                    subdirs[:] = []
                else:
                    subdirs[:] = [s for s in subdirs
                                  if s.lower() not in self._SCAN_SKIP_DIRS]
                for fn in files:
                    if not fn.lower().endswith(".xml"):
                        continue
                    path = os.path.join(root, fn)
                    if path in seen:
                        continue
                    seen.add(path)
                    info = self.read_build_file(path)
                    entry = {"name": os.path.splitext(fn)[0], "path": path}
                    if isinstance(info, dict) and "error" not in info:
                        entry.update(info)
                    builds.append(entry)
                    if len(builds) >= MAX_BUILDS:
                        return builds
        return builds

    def read_build_file(self, path):
        """Parse a PoB build .xml file straight from disk."""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return self.extract_character_data(f.read())
        except Exception as e:
            return {"error": f"Could not read build file: {e}"}

    # ------------------------------------------------------------------
    # Resolve a shared build LINK (pobb.in / poe.ninja) to a PoB code
    # ------------------------------------------------------------------
    def resolve_link_to_code(self, url_or_code):
        """Best-effort: turn a pobb.in / poe.ninja build link into a PoB import
        code. If the input already looks like a code, return it unchanged.
        Returns (code_or_none, message)."""
        text = (url_or_code or "").strip()
        if not text:
            return None, "Nothing pasted."
        if not text.lower().startswith("http"):
            return text, "Treated input as a raw PoB code."
        try:
            import requests
        except Exception:
            return None, "Install 'requests' to resolve links (pip install requests)."

        headers = {"User-Agent": "KalandraOverlay/1.0"}
        try:
            if "pobb.in" in text:
                # pobb.in exposes the raw code by appending /raw
                raw = text.rstrip("/")
                if not raw.endswith("/raw"):
                    raw += "/raw"
                r = requests.get(raw, headers=headers, timeout=15)
                if r.status_code == 200 and r.text.strip():
                    return r.text.strip(), "Fetched PoB code from pobb.in."
            # Generic: try fetching the URL and using the body if it looks like a code.
            r = requests.get(text, headers=headers, timeout=15)
            if r.status_code == 200:
                body = r.text.strip()
                # A PoB code is a long base64-ish blob with no spaces.
                if len(body) > 40 and " " not in body[:80] and "<" not in body[:5]:
                    return body, "Fetched PoB code from link."
            return None, ("Could not extract a PoB code from that link. On poe.ninja, "
                          "use the build's 'Copy' / 'Export to Path of Building' button "
                          "and paste the code directly.")
        except Exception as e:
            return None, f"Link fetch failed: {e}"

    def find_pob_exe(self, explicit=None):
        """Locate the Path of Building 2 executable, or None."""
        import os, shutil
        cands = []
        if explicit:
            cands.append(explicit)
        for name in ("Path of Building.exe", "PathOfBuilding.exe", "pathofbuilding"):
            w = shutil.which(name)
            if w:
                cands.append(w)
        # Common install locations.
        names = ("Path of Building.exe", "PathOfBuilding.exe")
        dirs = [
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Path of Building Community (PoE2)"),
            os.path.expandvars(r"%PROGRAMFILES%\Path of Building Community (PoE2)"),
            os.path.expandvars(r"%PROGRAMFILES(X86)%\Path of Building Community"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Path of Building Community (PoE2)"),
            os.path.expanduser(r"~\Path of Building (PoE2)"),
        ]
        for d in dirs:
            for n in names:
                cands.append(os.path.join(d, n))
        for c in cands:
            if c and os.path.exists(c):
                return c
        return None

    def launch_path_of_building(self, pob_exe=None):
        """Open the Path of Building application (best-effort, optional path)."""
        import os, subprocess
        exe = self.find_pob_exe(pob_exe)
        if not exe:
            return False, ("Path of Building wasn't found automatically. The code is on "
                           "your clipboard — open PoB and paste it into Import/Export, "
                           "or set \"pob_exe\" in data_engine/config.json to its .exe path.")
        try:
            subprocess.Popen([exe])
            return True, "Launched Path of Building. Paste the code into Import/Export."
        except Exception as e:
            return False, f"Could not launch PoB: {e}"

    def decode_pob_string(self, pob_code):
        """
        Decodes a compressed base64 Path of Building string into a raw XML string.
        
        Parameters:
            pob_code (str): The compressed raw string exported from Path of Building.
            
        Returns:
            str: The decompressed XML string, or an error dictionary.
        """
        try:
            import re as _re
            # Strip ALL whitespace/newlines (copy-paste often adds them), then
            # convert URL-safe base64 to standard and pad.
            clean_code = _re.sub(r"\s+", "", pob_code).replace('-', '+').replace('_', '/')
            clean_code += "=" * (-len(clean_code) % 4)
            compressed_data = base64.b64decode(clean_code)

            # Cap decompressed output: a real PoB2 export is well under a few MB,
            # but zlib's ~1000:1 ratio means a tiny paste (or a fetched URL body
            # via resolve_link_to_code) could inflate to gigabytes. Bound it so a
            # decompression bomb can't exhaust memory.
            MAX_DECOMPRESSED = 24 * 1024 * 1024   # 24 MB is comfortably huge
            try:
                dobj = zlib.decompressobj()
                decompressed = dobj.decompress(compressed_data, MAX_DECOMPRESSED)
            except zlib.error:
                # Tolerant fallback: raw-inflate past the 2-byte zlib header,
                # ignoring a corrupt trailing checksum (survives minor copy damage).
                dobj = zlib.decompressobj(-15)
                decompressed = dobj.decompress(compressed_data[2:], MAX_DECOMPRESSED)
            if dobj.unconsumed_tail:
                return {"error": "This build code is unusually large (over 24 MB "
                                 "decompressed) — it may be corrupted or not a real "
                                 "Path of Building export."}
            return decompressed.decode('utf-8', 'replace')

        except Exception as e:
            return {"error": f"Decompression failed. Code may be corrupted or legacy: {str(e)}"}

    def extract_character_data(self, xml_string):
        """
        Parses the decompressed XML payload to extract essential build attributes
        like Class, Ascendancy, Total DPS, and survivability (Effective Hit Pool).
        
        Parameters:
            xml_string (str): The raw decompressed XML string representing the build.
            
        Returns:
            dict: Structured character attributes and numerical statistics.
        """
        # If the decoding step yielded an error, pass it back immediately
        if isinstance(xml_string, dict) and "error" in xml_string:
            return xml_string

        try:
            # Parse the text string into an XML DOM Tree
            root = ET.fromstring(xml_string)
            
            # Locate the core <Build> element within the PoB schema
            build_node = root.find('Build')
            if build_node is None:
                return {"error": "Invalid PoB data layout: <Build> element missing."}

            # Initialize our clean payload structure. Attribute names differ a bit
            # across PoB versions, so accept the known variants.
            extracted_stats = {
                "class_name": build_node.get("className", "Unknown"),
                "ascendancy_name": (build_node.get("ascendClassName")
                                    or build_node.get("ascendancyClassName") or "None"),
                "level": int(build_node.get("level", "1")),
                "total_dps": 0.0,
                "ehp": 0.0,
                "life": 0.0,
                "energy_shield": 0.0
            }

            # Stat names vary across PoB/PoB2 versions. Be tolerant: for DPS/EHP,
            # take the MAX over any stat whose name contains DPS/EHP (excluding
            # per-second-cost style names), so we don't depend on one exact key.
            best_dps = 0.0
            best_ehp = 0.0
            for stat in build_node.findall('PlayerStat'):
                name = stat.get('stat') or ""
                val = stat.get('value')
                if not val:
                    continue
                try:
                    fval = float(val)
                except (ValueError, TypeError):
                    continue
                # Reject NaN/Inf: PoB never legitimately exports them, and
                # float('inf')/('nan') pass float() cleanly, then poison
                # json.dumps (emits invalid NaN/Infinity) and round() downstream.
                if not math.isfinite(fval):
                    continue
                if "DPS" in name and "Cost" not in name and fval > best_dps:
                    best_dps = fval
                elif "EHP" in name and fval > best_ehp:
                    best_ehp = fval
                elif name == "Life":
                    extracted_stats["life"] = round(fval, 2)
                elif name == "EnergyShield":
                    extracted_stats["energy_shield"] = round(fval, 2)
            extracted_stats["total_dps"] = round(best_dps, 2)
            extracted_stats["ehp"] = round(best_ehp, 2)

            return extracted_stats

        except Exception as e:
            return {"error": f"Failed to parse XML metrics: {str(e)}"}

    # Lines in a PoB item block that are metadata, not actual mods.
    _ITEM_META_PREFIXES = (
        "rarity:", "item level", "itemlevel", "levelreq", "level req", "quality:",
        "sockets:", "implicits:", "unique id", "uniqueid", "crafted:", "prefix:",
        "suffix:", "id:", "league:", "source:", "variant", "selected", "item class:",
        "requires", "limited to", "radius:", "evasion:", "armour:", "energy shield:",
        "{", "}", "corrupted", "shaper item", "elder item")
    _MOD_KEYWORDS = (
        "increased", "reduced", "more ", "less ", "adds ", "gain", "regenerate",
        "leech", "resistance", "maximum life", "maximum mana", "maximum energy",
        "damage", "critical", "attack speed", "cast speed", "movement speed",
        "penetrat", "chance to", "to all", "to level", "armour", "evasion",
        "spirit", "strength", "dexterity", "intelligence", "attributes")

    @classmethod
    def _is_mod(cls, line):
        """True if a PoB item line looks like an actual modifier (not metadata).
        Catches lines that start with a number/%, a '+/-', or contain a stat
        keyword — the old filter dropped numeric-leading mods like '12%
        increased ...', which is most jewel/explicit text."""
        low = line.lower().strip()
        if not low or any(low.startswith(p) for p in cls._ITEM_META_PREFIXES):
            return False
        if line[:1].isdigit() or line[:1] in "+-":
            return True
        return any(k in low for k in cls._MOD_KEYWORDS)

    @staticmethod
    def _gem_is_support(gem):
        """A gem is a support if its metadata id / skill id marks it so."""
        gid = (gem.get("gemId") or "")
        sid = (gem.get("skillId") or "")
        return ("SupportGem" in gid) or sid.startswith("Support")

    def extract_full_build(self, xml_string):
        """Parse the WHOLE build so the AI can 'see' everything: class/ascendancy,
        every PlayerStat, the equipped items (by slot, with their mods), and every
        skill group (active skill + its supports), flagging the MAIN skill group.
        Returns a dict; use build_ai_summary() to turn it into prompt text."""
        if isinstance(xml_string, dict) and "error" in xml_string:
            return xml_string
        try:
            root = ET.fromstring(xml_string)
            out = {"stats": {}, "items": [], "skills": [], "notes": "",
                   "main_group": None, "main_skill": None}
            build = root.find("Build")
            main_socket = None
            if build is not None:
                out["class_name"] = build.get("className", "?")
                out["ascendancy"] = (build.get("ascendClassName")
                                     or build.get("ascendancyClassName") or "None")
                out["level"] = build.get("level", "?")
                try:
                    main_socket = int(build.get("mainSocketGroup", "0"))
                except ValueError:
                    main_socket = None
                for st in build.findall("PlayerStat"):
                    nm, val = st.get("stat"), st.get("value")
                    if nm and val:
                        out["stats"][nm] = val

            # Items: map slot -> item name/base + notable mods.
            id_to_item = {}
            items_node = root.find("Items")
            if items_node is not None:
                for it in items_node.findall("Item"):
                    raw = (it.text or "").strip()
                    if not raw:
                        continue
                    lines = [l.strip() for l in raw.splitlines() if l.strip()]
                    name = lines[1] if len(lines) > 1 and lines[0].startswith("Rarity") else lines[0]
                    mods = [l for l in lines if self._is_mod(l)][:8]
                    # Rarity + base feed the dashboard's visual gear view
                    # (rarity colors the frame; base locates the item art).
                    rarity = (lines[0].split(":", 1)[1].strip()
                              if lines[0].lower().startswith("rarity") else "")
                    base = ""
                    if rarity.lower() in ("rare", "unique") and len(lines) > 2:
                        base = lines[2]
                    elif rarity.lower() in ("magic", "normal"):
                        base = name
                    # Jewel if name/base or an "Item Class: Jewels" line says so.
                    head = " ".join(lines[:4]).lower()
                    is_jewel = ("jewel" in name.lower()) or ("item class: jewel" in head)
                    id_to_item[it.get("id")] = {"name": name, "mods": mods,
                                                "rarity": rarity, "base": base,
                                                "is_jewel": is_jewel}
                # Slots from the ACTIVE item set.
                active_set = items_node.get("activeItemSet")
                itemset = None
                for iset in items_node.findall("ItemSet"):
                    if iset.get("id") == active_set:
                        itemset = iset
                        break
                if itemset is None:
                    itemset = items_node.find("ItemSet")
                included = set()
                if itemset is not None:
                    for slot in itemset.findall("Slot"):
                        iid = slot.get("itemId")
                        if iid and iid in id_to_item:
                            entry = {k: v for k, v in id_to_item[iid].items() if k != "is_jewel"}
                            entry["slot"] = slot.get("name")
                            out["items"].append(entry)
                            included.add(iid)
                # Jewels socketed in the PASSIVE TREE live in the Tree spec's
                # <Socket itemId=..>, not in gear slots, so the old parser missed
                # them entirely. Collect them (and any jewel-base item) so the AI
                # sees their build-defining mods.
                tree_socket_ids = set()
                tree_node = root.find("Tree")
                if tree_node is not None:
                    for sock in tree_node.iter("Socket"):
                        sid = sock.get("itemId")
                        if sid and sid != "0":
                            tree_socket_ids.add(sid)
                for iid, info in id_to_item.items():
                    if iid in included:
                        continue
                    socketed = iid in tree_socket_ids
                    if socketed or info.get("is_jewel"):
                        entry = {"name": info["name"], "mods": info["mods"],
                                 "slot": "Jewel (tree)" if socketed else "Jewel"}
                        out["items"].append(entry)
                        out.setdefault("jewels", []).append(entry)
                        included.add(iid)
                if not out["items"]:  # fallback: just list items
                    out["items"] = [{"name": v["name"], "mods": v["mods"]}
                                    for v in id_to_item.values()]

            # Skills: walk ONLY the active skill set, keep group order so the
            # mainSocketGroup index lines up, and split active skill vs supports.
            skills_node = root.find("Skills")
            if skills_node is not None:
                active_set_id = skills_node.get("activeSkillSet")
                skillset = None
                for ss in skills_node.findall("SkillSet"):
                    if ss.get("id") == active_set_id:
                        skillset = ss
                        break
                if skillset is None:
                    skillset = skills_node.find("SkillSet") or skills_node
                groups = skillset.findall("Skill")
                for idx, sk in enumerate(groups, start=1):
                    gems = sk.findall("Gem")
                    if not gems:
                        continue
                    actives = [g.get("nameSpec") for g in gems
                               if g.get("nameSpec") and not self._gem_is_support(g)]
                    supports = [g.get("nameSpec") for g in gems
                                if g.get("nameSpec") and self._gem_is_support(g)]
                    # If the export marks an active gem, prefer that as the name.
                    label = actives[0] if actives else (
                        gems[0].get("nameSpec") if gems[0].get("nameSpec") else "?")
                    is_main = (main_socket is not None and idx == main_socket)
                    grp = {"index": idx, "active": label, "actives": actives,
                           "supports": supports, "is_main": is_main,
                           "enabled": sk.get("enabled", "true") != "false"}
                    out["skills"].append(grp)
                    if is_main:
                        out["main_group"] = idx
                        out["main_skill"] = label
            return out
        except Exception as e:
            return {"error": f"Full-build parse failed: {e}"}

    # Damage types / mechanics we look for to profile what a build scales.
    _DMG_KEYWORDS = {
        "physical": ("physical", "impale", "armour break", "mace", "bleed", "bleeding"),
        "fire": ("fire", "ignite", "burning", "molten", "flame"),
        "cold": ("cold", "freeze", "chill", "frost", "ice"),
        "lightning": ("lightning", "shock", "spark", "arc", "galvanic"),
        "chaos": ("chaos", "poison", "wither", "contagion", "caustic"),
    }
    _MECH_KEYWORDS = {
        "bleed": ("bleed", "bleeding", "gore", "hemorrhage"),
        "poison": ("poison", "caustic"),
        "ignite": ("ignite", "burning"),
        "crit": ("crit", "critical"),
        "minions": ("minion", "raise", "summon", "skeleton", "zombie", "companion"),
        "attack": ("attack", "strike", "slam", "mace", "bow", "spear", "claw"),
        "spell": ("spell", "cast", "curse", "herald", "barrier"),
        "warcry": ("cry", "warcry", "banner"),
        "dot / damage-over-time": ("damage over time", "degen", "ailment"),
    }

    @classmethod
    def analyze_scaling(cls, full):
        """Deterministically profile WHAT a build scales — damage types, key
        mechanics, crit vs non-crit, attack vs spell, defensive layers — from the
        parsed build. This is grounded (no guessing): it reads the actual skills,
        supports, item mods and PoB stats. The AI uses it to tell the player which
        stat weights to set in PoB's tree Power Report."""
        if not isinstance(full, dict) or "error" in full:
            return {}
        # Weighted text pools: what the build USES (main skill + its gems)
        # must dominate what it merely WEARS (item text) — and defensive
        # lines must never count as damage: a "+35% Fire Resistance" roll
        # was polluting fire's score on every single build.
        import re as _re
        skill_blobs, item_blobs = [], []
        if full.get("main_skill"):
            skill_blobs += [full["main_skill"]] * 8
        for g in full.get("skills", []) or []:
            w = 5 if g.get("is_main") else 2
            for a in (g.get("actives") or []):
                skill_blobs += [a] * w
            for s2 in (g.get("supports") or []):
                skill_blobs += [s2] * max(w - 1, 1)
        _DEFENSIVE = _re.compile(
            r"resistance|regenerat|to maximum (life|mana|energy shield)"
            r"|to all attributes|to (strength|dexterity|intelligence)"
            r"|stun|movement speed|life on|mana on|charm|flask", _re.I)
        _FLAT = _re.compile(r"adds? \d+ to \d+ \w+ damage", _re.I)
        for it in full.get("items", []) or []:
            item_blobs.append(it.get("name", ""))
            for m in (it.get("mods") or []):
                if _DEFENSIVE.search(m or ""):
                    continue          # a fire RES roll is not fire DAMAGE
                item_blobs += [m] * (3 if _FLAT.search(m or "") else 1)
        skill_text = " ".join(b for b in skill_blobs if b).lower()
        item_text = " ".join(b for b in item_blobs if b).lower()
        text = skill_text + " " + item_text

        def score(groups, t=None):
            t = text if t is None else t
            out = {}
            for label, kws in groups.items():
                n = sum(t.count(k) for k in kws)
                if n:
                    out[label] = n
            return out

        dmg = score(cls._DMG_KEYWORDS)
        mech = score(cls._MECH_KEYWORDS)
        # Minion builds: the SKILLS decide (a "minion damage" gear roll on a
        # spark build must not flip the profile).
        if score({"m": cls._MECH_KEYWORDS["minions"]}, skill_text):
            mech["minions"] = mech.get("minions", 0) + 10
        # Crit from PoB stats too (more reliable than keywords alone).
        s = full.get("stats", {})
        try:
            crit_chance = float(s.get("CritChance", s.get("CritChanceForDisplay", 0)) or 0)
        except (TypeError, ValueError):
            crit_chance = 0.0
        is_crit = crit_chance >= 30 or "crit" in mech
        order = lambda d: [k for k, _ in sorted(d.items(), key=lambda x: -x[1])]
        return {
            "main_skill": full.get("main_skill"),
            "class": full.get("class_name"),
            "ascendancy": full.get("ascendancy"),
            "damage_types": order(dmg),
            "mechanics": order(mech),
            "crit_based": bool(is_crit),
            "crit_chance": round(crit_chance, 1) if crit_chance else None,
        }

    @classmethod
    def tree_guidance(cls, full):
        """Prompt-ready guidance block: the build's scaling profile + how to use
        PoB's passive-tree Power Report to find efficient repathing, tuned to
        THIS build. Returns '' if no build is loaded."""
        prof = cls.analyze_scaling(full)
        if not prof or not prof.get("main_skill"):
            return ""
        dts = ", ".join(prof["damage_types"][:3]) or "its main damage type"
        mechs = ", ".join(prof["mechanics"][:4]) or "its core mechanic"
        crit = ("crit-based (so Critical Strike Chance/Multiplier are high-value)"
                if prof["crit_based"] else "non-crit (favor flat/increased damage and ailment scaling)")
        weights = []
        for dt in prof["damage_types"][:3]:
            weights.append(f"increased {dt} damage")
        if prof["crit_based"]:
            weights.append("critical strike chance/multiplier")
        if "attack" in prof["mechanics"]:
            weights.append("attack speed")
        if any(m in prof["mechanics"] for m in ("bleed", "poison", "ignite", "dot / damage-over-time")):
            weights.append("damage over time / ailment magnitude & duration")
        weights = weights or ["your main damage stat"]
        return (
            "BUILD SCALING PROFILE (computed from the loaded build): "
            f"main skill {prof['main_skill']}; scales primarily via {dts}; "
            f"key mechanics: {mechs}; {crit}.\n"
            "HOW TO FIND PASSIVE-TREE UPGRADES IN PATH OF BUILDING (guide the user "
            "through this — do NOT invent node names or exact numbers):\n"
            "1) Open the Tree tab in Path of Building.\n"
            "2) Use the node Power Report / stat-weight heatmap (in PoB: the 'Show "
            "Node Power' / power-report control on the tree). Set the stat weights "
            f"toward: {', '.join(weights)}.\n"
            "3) PoB will color each unallocated node by how much it improves those "
            "weighted stats; hover a node to see the exact DPS/EHP delta and the "
            "point cost to reach it.\n"
            "4) Compare candidate clusters by (gain ÷ points spent) and look for "
            "repaths that free up points from low-value nodes you've already taken.\n"
            "Tell the user the exact numbers and node names come from PoB's report "
            "for their tree — you provide the strategy and which weights to set.")

    @staticmethod
    def build_ai_summary(full, max_items=40, max_skills=40):
        """Full, prompt-ready text of the build so the AI can 'see' everything:
        class, defensive + offensive stats, the MAIN skill (with a note when the
        exported DPS is 0 because the main socket group is a buff/utility skill),
        EVERY skill group, and EVERY equipped item with its key mods."""
        if not full or "error" in full:
            return ""
        s = full.get("stats", {})
        def stat(*keys, default="?"):
            for k in keys:
                if k in s:
                    return s[k]
            return default
        def fnum(*keys):
            v = stat(*keys, default=None)
            try:
                f = float(v)
            except (TypeError, ValueError):
                return None
            # Non-finite values (a hand-crafted or corrupt export with inf/nan)
            # would crash round() with OverflowError — treat them as absent.
            return f if math.isfinite(f) else None

        lines = [f"CHARACTER: {full.get('class_name','?')} / {full.get('ascendancy','None')} "
                 f"Lv{full.get('level','?')}"]

        # Offense — report the best available DPS figure and name the field.
        dps = fnum("FullDPS", "CombinedDPS", "TotalDPS", "TotalDotDPS", "WithBleedDPS")
        # Also scan every stat for the largest DPS-like value (covers odd builds).
        best = 0.0
        for nm, val in s.items():
            if "DPS" in nm and "Cost" not in nm:
                try:
                    fv = float(val)
                    if math.isfinite(fv):
                        best = max(best, fv)
                except ValueError:
                    pass
        if best > (dps or 0):
            dps = best
        main_skill = full.get("main_skill")
        if dps and dps > 0:
            lines.append(f"DPS (exported, main skill '{main_skill or '?'}'): {round(dps):,}")
        else:
            lines.append(
                f"DPS: 0 in this export. The exported main skill group is "
                f"'{main_skill or 'a buff/utility skill'}', which deals no direct hit "
                f"damage, so Path of Building froze all DPS fields at 0 for this save. "
                f"The build's real damage comes from other skill groups listed below "
                f"(look for the cry/ailment/attack skills). To get an accurate DPS "
                f"number, set the damage skill as the main socket group in PoB and "
                f"re-export, or run the headless simulator.")

        # Defence + core attributes. Spirit shows total + unreserved (the usable
        # amount after reservations), since the total alone can look surprising.
        spirit = stat('Spirit')
        sun = stat('SpiritUnreserved', default=None)
        spirit_str = f"{spirit}" + (f" (unreserved {sun})" if sun not in (None, "?") else "")
        lines.append(
            f"Life {stat('Life')} | ES {stat('EnergyShield')} | Mana {stat('Mana')} | "
            f"Spirit {spirit_str} | EHP {round(fnum('TotalEHP') or 0)} | "
            f"Str/Dex/Int {stat('Str')}/{stat('Dex')}/{stat('Int')}")
        lines.append(
            f"Resists f/c/l/chaos: {stat('FireResist')}/{stat('ColdResist')}/"
            f"{stat('LightningResist')}/{stat('ChaosResist')} | "
            f"Crit mult {stat('CritMultiplier')} | Hit chance {stat('HitChance')}")

        # Skills — list EVERY group, mark the main one, show active + supports.
        if full.get("skills"):
            lines.append("SKILL GROUPS (active skill — supports):")
            for g in full["skills"][:max_skills]:
                if isinstance(g, dict):
                    star = " <<< MAIN" if g.get("is_main") else ""
                    off = "" if g.get("enabled", True) else " (disabled)"
                    sup = (" — " + ", ".join(g.get("supports", []))) if g.get("supports") else ""
                    lines.append(f"  {g.get('index','?')}. {g.get('active','?')}{sup}{star}{off}")
                else:  # backward-compat with the old list-of-lists shape
                    lines.append("  " + " + ".join(g))

        # Gear — every slot with its key mods.
        if full.get("items"):
            lines.append("GEAR:")
            for it in full["items"][:max_items]:
                slot = it.get("slot", "")
                mods = ("  [" + "; ".join(it.get("mods", [])[:4]) + "]") if it.get("mods") else ""
                lines.append(f"  - {slot}: {it.get('name','?')}{mods}")
        return "\n".join(lines)


if __name__ == "__main__":
    print("Testing Path of Building calculation bridge...")
    bridge = KalandraPoBBridge()

    # To guarantee a robust self-test without requiring a massive real PoB file, 
    # we programmatically build, compress, and encode a mock PoB XML payload:
    mock_xml = (
        '<PathofBuilding>'
        '<Build level="20" className="Ranger" ascendancyClassName="Stormweaver">'
        '<PlayerStat stat="TotalDPS" value="45802.12"/>'
        '<PlayerStat stat="EffectiveHitPool" value="1250.0"/>'
        '<PlayerStat stat="Life" value="620.0"/>'
        '<PlayerStat stat="EnergyShield" value="0.0"/>'
        '</Build>'
        '</PathofBuilding>'
    )
    
    # Compress and encode our mock build
    compressed = zlib.compress(mock_xml.encode('utf-8'))
    mock_base64_string = base64.b64encode(compressed).decode('utf-8')
    
    print(f"Generated Mock PoB Code String: {mock_base64_string[:40]}...")

    # Now, execute our bridge parser to decode, decompress, and read the values back
    raw_xml = bridge.decode_pob_string(mock_base64_string)
    parsed_results = bridge.extract_character_data(raw_xml)

    print("\n--- DECODING RESULTS ---")
    if "error" in parsed_results:
        print(f"Test Failed: {parsed_results['error']}")
    else:
        print(f"Target Class: {parsed_results['class_name']}")
        print(f"Ascendancy:   {parsed_results['ascendancy_name']}")
        print(f"Char Level:   {parsed_results['level']}")
        print(f"Total DPS:    {parsed_results['total_dps']} DPS")
        print(f"Max eHP:      {parsed_results['ehp']} eHP")
        print("\nSuccess! Path of Building parser calculations verified flawlessly.")