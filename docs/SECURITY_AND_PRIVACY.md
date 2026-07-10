# Kalandra Overlay — Security & Privacy Posture

This document is an honest assessment of how the app handles your safety, your
data, and your machine's resources — and what must still be done **before** it
would be safe to distribute publicly or sell. It is written so a non-specialist
can follow it.

---

## 1. Where your secrets live

- API keys (OpenAI/Gemini/…), your POESESSID, the OBS websocket password and
  the GitHub token are stored in your operating system's **credential vault**
  via the `keyring` library — Windows Credential Manager on your PC. They are
  **never** written to the project folder in plain text and **never** printed
  to the console or logs.
- **Fail closed (shipped):** the old plaintext `.secrets.json` fallback was
  removed. If `keyring` is unavailable, saving secrets is **refused** rather
  than written to a file.
- Nothing is uploaded to us or any server we control. There is no telemetry.
- The user-facing privacy policy (what's local vs what goes to your chosen AI
  provider) lives in **`docs/PRIVACY.md`**.

## 2. What leaves your computer (privacy)

- **Voice:** your microphone audio is transcribed **locally** on your PC by
  Whisper. The raw audio never leaves the machine. Only the resulting **text**
  (plus relevant snippets from your local database) is sent to the cloud AI
  **you** chose, using **your** key. If you use no key, nothing is sent.
- **Screen recording / snapshots:** saved only to `data_engine/` on your disk.
  Nothing is uploaded. (For a public release, recording should show a clear
  recording indicator and obtain consent — important legally.)
- **Web scraping:** outbound requests go only to a fixed set of known hosts
  (poe2db.tw, poe2wiki.net, poe.ninja, pathofexile.com). All requests send a
  descriptive User-Agent and have timeouts.

## 3. Process & resource safety (no runaway / no bloat)

- Long jobs (crawl, recording, transcription) run on **daemon threads** that die
  with the app, are **cancelable** (click the sync medallion again to pause), and
  each runs **one at a time** guarded by a state flag.
- The crawler **self-throttles** (~0.6s/request), **caches** responses, respects
  a **persistent frontier** so it never re-fetches, and is bounded by a safety
  cap (max ~30k pages per run) so it can't loop forever.
- Each background worker uses **its own database connection** (the recent SQLite
  cross-thread crash is fixed by this), so threads don't corrupt shared state.
- Heavy dependencies (Whisper, OpenCV) are **optional and lazily imported**; if a
  user doesn't install them, those features simply report a hint instead of
  bloating startup. Whisper model size and recording FPS are configurable.

## 4. Current weaknesses (be honest)

- **No input hardening on the AI key field** beyond storing it; a malformed key
  just fails the API call. Fine for personal use.
- **POESESSID** is a live login session token. Storing it (even in keyring) is
  sensitive; if your machine is compromised, so is that token. We only request it
  when you opt in, and it is never logged — but users must understand the risk.
- **Dependencies are not pinned/audited** for known CVEs. Before shipping, pin
  exact versions and run `pip-audit` regularly.
- **No code signing.** An unsigned `.exe` will trip Windows SmartScreen and could
  be tampered with in transit.
- **CC BY-NC content** (poe2wiki) is fine for personal use but **non-commercial** —
  selling a product that redistributes that content needs licensing review.
- **Site terms of service**: scraping is currently limited to sites that permit it
  (poe2db, poe2wiki) plus public APIs (poe.ninja). A commercial product must get
  this reviewed per-site; some explicitly forbid commercial reuse.

## 5. Checklist before going public / commercial

1. Remove the plaintext secrets fallback; require keyring (fail closed).
2. Pin every dependency to an exact version; add `pip-audit` to CI.
3. Code-sign the Windows build; ship an integrity-checked auto-updater.
4. Add a clear, visible **recording indicator** and a first-run privacy consent.
5. Legal review of each data source's ToS for **commercial** use, and of CC-BY-NC
   content redistribution.
6. Add a privacy policy stating exactly what is processed locally vs sent to the
   chosen AI provider (and that the provider's own terms then apply).
7. Sandbox/limit filesystem writes to a single app data directory.
8. Rate-limit and cache all external calls (already done) and add backoff.
9. Consider GDPR/CCPA if you ever collect any user data server-side (currently
   you collect none — keep it that way unless necessary).

## 6. Summary

For **personal use today**, the posture is reasonable: secrets in the OS vault,
local-first processing, no telemetry, bounded/cancelable background work, and
fixed outbound hosts. For a **public/commercial** release, the items in section 5
— especially removing the plaintext fallback, dependency auditing, code signing,
recording consent, and ToS/licensing review — are the gating work.
