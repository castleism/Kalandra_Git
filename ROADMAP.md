# Kalandra Overlay — Roadmap to a Sellable Product

Status of the security/compliance "gating work" identified in
`SECURITY_AND_PRIVACY.md`, plus the data/feature roadmap.

## Gating work (must-haves before selling)

| Item | Status | Effort | Notes |
|---|---|---|---|
| Remove plaintext secrets fallback (fail closed) | ✅ DONE | — | `account_manager` now stores only in the OS keychain; if keyring is missing, saving is disabled (no plaintext file). |
| Visible recording indicator + consent | ✅ DONE | — | Red “● REC” while recording; one-time consent dialog before first capture. |
| Pin & audit dependencies | ◑ PARTIAL | low | Add a committed `requirements-lock.txt` (exact versions) and run `pip-audit` in CI. Floors are set; full lock pending so 3.13 wheels keep resolving. |
| Code-sign the Windows build | ☐ TODO | med ($) | Requires an Authenticode cert (~$100–400/yr) + signing in the build pipeline. Removes SmartScreen warnings. |
| Per-site ToS / licensing review | ☐ TODO | med (legal) | Especially: poe2wiki is **CC BY-NC** (non-commercial) — redistributing it in a paid product needs review/relicensing. Confirm poe2db, poe.ninja, Craft of Exile commercial terms. |
| Privacy policy | ☐ TODO | low | State what's processed locally vs sent to the chosen AI provider. |
| Sandboxed file writes | ◑ PARTIAL | low | All writes already go under `data_engine/`; formalize + document. |

### How to do the dependency audit now (low-hanging)
```
pip install pip-audit
pip-audit -r requirements.txt
pip freeze > requirements-lock.txt   # commit this for reproducible installs
```

## Feature roadmap

| Feature | Status |
|---|---|
| Five medallion buttons aligned | ✅ |
| Real MP4 screen recording (+ consent/indicator) | ✅ |
| Local voice transcription (Whisper) | ✅ |
| poe2db crawler with persistent, resumable frontier | ✅ |
| poe2wiki (MediaWiki API) scraping | ✅ |
| poe.ninja economy snapshots | ✅ |
| Obsidian vault export with relationship links | ✅ |
| AI brain (OpenAI/Gemini) + key helpers + README | ✅ |
| Talking orb lip-sync (jaw-drop from 2D art) | ✅ |
| Characters via PoB code/link + saved-builds folder | ✅ |
| Game-file data extraction | ◑ Import of pre-extracted JSON done; in-process Oodle bundle decode TODO |
| Your own (non-ladder) PoE2 characters via API | ☐ Blocked on GGG shipping the PoE2 OAuth API |
| Higher-fidelity face rig (layered art, blinks) | ☐ Optional upgrade — drop in layered mouth/eye art |

## Next candidates
1. Lock + audit dependencies (quick win).
2. Layered face art for the orb (closed/mid/open mouth PNGs) for crisper lip-sync.
3. Game-file extraction: integrate a bundled extractor binary so step 1 is automatic.
4. Revisit GGG OAuth when the PoE2 API ships, for personal character import.
