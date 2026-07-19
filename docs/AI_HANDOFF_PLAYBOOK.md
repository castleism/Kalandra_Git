# AI Handoff Playbook — which model to use when Claude credits run dry

Purpose: keep Kalandra moving all week. This maps roadmap/checklist items to the
AI tool that does each job **better or cheaper than a general coding assistant**,
so when the weekly Claude/Cowork budget is spent you switch lanes instead of
stopping. (Tool names checked July 2026 — this landscape shifts fast; re-verify
quarterly.)

**Rule of thumb:** Claude-in-Cowork is the only tool in this list with direct
access to the repo on disk, the test suites, and the session history — so save
it for *multi-file engine work, bug fixes, and anything that must run tests*.
Everything below is work you can carry OUT of the repo as a self-contained
brief, do elsewhere, and carry back as files.

---

## 1. Art & visual assets → image-generation models

**Best tools right now:** GPT Image 2 (in ChatGPT), Nano Banana Pro (in
Gemini), Midjourney, FLUX.2. For icon sets where every piece must match, GPT
Image 2 and Nano Banana Pro follow reference images and multi-image consistency
instructions best; Midjourney wins on ornate painterly texture (very on-brand
for gold-leaf Kalandra).

| Roadmap item | What to generate | Handoff brief |
|---|---|---|
| **W3-03 theme asset kit (remainder)** | Tab-header orb icons, gem-accent button art, gold flourishes/dividers | Upload `Window.png` + `divine_orb.png` as style refs. Ask for: "matching icon set, transparent PNG, 128×128, gold-leaf + obsidian palette (#c9a227/#1d1526), one per: terminal, build, sim, reserve, price, exchange, crafting, filter, issues." Drop results in `gui_overlay/assets/theme/`. |
| **Companion orb art gaps** (`orbs/2d/<slug>.png`) | Missing currency orbs (anything Settings labels "(no art yet)") | Upload 2–3 existing orb PNGs as refs; request same rendering style, transparent background, centered, ~512×512. Filename = slug (e.g. `chance.png`). |
| **Viseme mouth sprites** (`docs/VISEME_FACE_SETUP.md`) | Rhubarb mouth shapes A–H,X for the orb face | One consistent sprite sheet request: "9 mouth shapes for lip-sync on a golden orb face, same lighting, transparent PNGs." Slice + drop in `assets/visemes/`. |
| **Owl guide layered art** | Blink frames / expression variants of `owl_face.png` | Upload the existing owl; ask for closed-eye + half-blink variants, identical framing. |
| Icon/branding odds & ends | Store banner, README hero image, `kalandra.ico` variants | Any of the above tools; ico conversion is a one-liner locally. |

**NOT an AI job:** W4-15 installer tab previews — those must be *real
screenshots* of your dashboard (blocked on your captures, per the roadmap).

## 2. 3D models → text/image-to-3D services

**Best tools right now:** Meshy, Tripo, Rodin — all export `.glb`.

| Roadmap item | Handoff brief |
|---|---|
| **W4-13 — 3D companion orbs** (`assets/orbs/3d/<slug>.glb`) | Feed each 2D orb PNG as an image-to-3D input; ask for a game-ready low-poly `.glb` with PBR gold material. The code path already looks for `assets/orbs/3d/<slug>.glb`, so this is pure asset work — zero code needed until the QtQuick3D loader lands. |

## 3. Video understanding → Gemini (long-context multimodal)

Gemini remains the strongest at "watch this clip and tell me what happened,"
and it's the cheapest way to *prototype* before writing any opencv code.

| Roadmap item | Handoff brief |
|---|---|
| **W3-34 — video fight analyzer** (phases 1–3) | Before building HP-bar pixel tracking, upload 2–3 death/boss MP4s from `data_engine/clips/` to Gemini and ask it to timestamp: boss HP %, visible buffs/debuffs, ground effects, the killing blow. Use its answers as the labeled ground truth your opencv code must match. |
| **W4-21 — death review autopsy enrichment** | Same trick per death clip: "list every avoidable mistake in this 20s clip with timestamps." Compare against the evidence-only PoB audit to decide what's worth automating. |
| **W4-10 — stream transcription → guide log** | Long VODs: Gemini for hour-scale video; plain audio can stay on local Whisper (free). |

## 4. Creative writing & persona copy → any strong chat model (cheap tier)

This is interchangeable commodity work — use GPT (ChatGPT) or Gemini free/cheap
tiers and save Claude budget. Paste the persona brief once per session:
*"You write for Kalandra, a PoE2 overlay. The Divine Orb: wry, confident,
theatrical, never mean, PoE flavor, 'exile' address, max 2 sentences per line."*

| Item | Notes |
|---|---|
| Divine Orb barks (greetings, sync-finished, death quips, budget warnings) | Ask for 50 at a time, pick the top 10. |
| Owl guide bubbles + interview copy (W4-02), new-player arc dialogue (W4-19) | Include the chip-answer constraints from `owl_interview.py`. |
| Store page / README hero copy / trailer script | Marketing tone work — GPT is excellent here. |
| Changelog → human release notes | Paste `CHANGELOG.md` chunks, ask for player-facing notes. |
| GGG outreach / OAuth application polish | Low volume, any model. |

## 5. Batch data labeling → cheap API models *inside Kalandra itself*

Kalandra already speaks to 6 providers — use the cheapest good one
(Gemini Flash-class or GPT mini-class) **via the app's own key slots** for:

| Item | Notes |
|---|---|
| **W4-30 P1.5 — tag extraction** for uniques/mods/passives (only gems are tagged today) | Classic batch classification; thousands of rows at fractions of a cent. Route through `tag_graph`'s pipeline; verify samples via the W4-32 quest board. |
| **Localized item headers** (tester finding E5: German/Russian pastes silently under-parse) | Have a cheap model emit the `Item Class:`/`Rarity:` header translation table for all client languages; wire it into `parse_item_text` as data, not code. |
| **W4-06 — nerf intel patch-note diffing** | Summarize patch notes into structured buffs/nerfs JSON on a cheap model; `nerf_intel.py` already consumes the structure. |
| Corrections-layer candidates | Cheap model proposes; a human (or Claude session) verifies before anything enters the verified layer. |

## 6. Voice & audio → specialist audio tools

| Item | Tool |
|---|---|
| **ElevenLabs voices** (roadmap "next up") | ElevenLabs itself — design the Divine Orb voice in their voice designer; it plugs in as the premium tier above the free Kalandra Voice (Piper) that shipped 2026-07-12. |
| SFX (chimes, craft alarms, UI ticks) | ElevenLabs SFX generation; seconds-long WAVs, drop into `assets/sfx/`. |
| Ambient/menu music | Suno (or similar music model) if you ever want a Kalandra theme. |

## 7. Keep for Claude-in-Cowork (don't hand these off)

- The open bug list from Tester Session #0 (filter-editor byte fidelity, test
  battery repairs, provider seam, price-honesty gate) — multi-file, test-gated.
- PoB bridge / pob_sim / LuaJIT engine work — needs the repo + test suites.
- Installer & release tooling, anything touching the keychain/fail-closed rules.
- Any change where "run `tests/stress_test.py` before committing" is the safety
  net — the other tools can't run your tests.

## Weekly rhythm suggestion

Claude credits fresh → burn them on engine/bug/test work (section 7).
Credits low → switch to sections 1–6: art queue in ChatGPT/Gemini/Midjourney,
3D queue in Meshy/Tripo, dialogue batches in GPT, labeling batches through
Kalandra's own cheap-provider keys. Park every produced asset in the right
folder; next Claude session wires anything that needs wiring.
