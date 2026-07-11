# Gating Research — code signing, licensing, trade-API boundaries

*Researched 2026-07-10 via a 102-agent verified-research pass (5 search
angles, 20 sources fetched, 94 claims extracted, 25 adversarially verified:
23 confirmed / 2 refuted-and-excluded). Everything below cites primary
sources. This is research, not legal advice.*

> **Rev 2 (2026-07-10, same day):** Christian set the business model —
> **Kalandra is free to the community**
> (recorded in `docs/VISION_ACQUISITION.md`). The verified facts below are
> unchanged, but the implications flip substantially in our favor, so each
> section now leads with the free-distribution reading. The paid-product
> analysis is kept as clearly-marked appendix guidance in case the stance
> ever changes.*

---

## 1. Code signing: the answer is Azure Artifact Signing, ~$10/month

**Verified (all 3–0 confirmations):**

- **Azure Artifact Signing** (formerly "Trusted Signing") Basic tier:
  **$9.99/month, 5,000 signatures included** ($0.005/signature overage),
  1 certificate profile of each type. Premium $99.99/mo (100k sigs, 10
  profiles). One price covers identity validation, certificate lifecycle,
  and signing — no other infrastructure.
  [pricing](https://azure.microsoft.com/en-us/pricing/details/artifact-signing/) ·
  [SKU docs](https://learn.microsoft.com/en-us/azure/artifact-signing/how-to-change-sku)
- **Fully managed, no hardware token.** Microsoft issues, holds (FIPS
  140-2 L3 HSMs), and auto-renews the cert; signing is remote digest
  signing (the exe never leaves your machine). Traditional OV/EV certs,
  by contrast, must live on a hardware token/HSM per post-June-2023
  CA/B Forum rules.
  [overview](https://learn.microsoft.com/en-us/azure/artifact-signing/overview)
- **Individuals are eligible** — self-employed developers included —
  via Entra Verified ID: government photo ID matching the order's
  name/address + a biometric selfie check. **Individual eligibility is
  currently limited to USA and Canada** (Christian qualifies).
  Onboarding was paused during 2025 and reopened at GA in 2026 with the
  old 3-year-business-history requirement dropped.
  [MS blog](https://techcommunity.microsoft.com/blog/microsoft-security-blog/trusted-signing-is-now-open-for-individual-developers-to-sign-up-in-public-previ/4273554) ·
  [FAQ](https://learn.microsoft.com/en-us/azure/artifact-signing/faq)

**Free-tool framing:** signing is about the SmartScreen "unknown
publisher" wall, not about selling — free tools face it identically, and
there is no $0 Authenticode path for closed-source software. Options:
(a) **ship unsigned — $0** — every new user clicks through the blue
SmartScreen warning; acceptable for early adopters, real friction against
"the tool the whole community installs"; (b) **Artifact Signing Basic,
~$120/yr** — the cheapest clean install experience, recommended once
adoption is the goal; (c) **open-source the repo** → SignPath's free OSS
signing becomes available. This row is now *recommended-not-gating* for a
free release. If/when signed: wire `signtool` + the Trusted Signing dlib
into `scripts/make_release_zip.py`. **Unverified residue:** exact 2026
OV/EV price cards and per-option SmartScreen reputation behavior didn't
survive verification — irrelevant unless the Azure path fails.

## 2. Licensing: mostly RESOLVED by the free-forever decision

**Verified (all 3–0):**

- **poe2wiki.net is CC BY-NC-SA 3.0 Unported.** NonCommercial bars uses
  "primarily intended for … commercial advantage or monetary
  compensation"; ShareAlike bars proprietary relicensing of derivatives.
  Redistributing scraped wiki content in a *paid* Kalandra violates both.
  [wiki copyrights](https://www.poe2wiki.net/wiki/Path_of_Exile_2_Wiki:Copyrights) ·
  [CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/)
- **poe2db.tw is ALSO CC BY-NC-SA 3.0** — its footer says so, and its own
  articles are reused downstream from Project PoE Wiki under that
  license, so poe2db *couldn't* grant us commercial rights even if asked.
  Its disclaimer further states GGG owns all IP in the game-derived
  material. **This overturns our earlier assumption that only the wiki
  was NC-encumbered.**
  [disclaimer](https://poe2db.tw/General_disclaimer) · [footer](https://poe2db.tw/us/)
- **GGG's Terms of Use** grant only a personal, *non-commercial* license
  to the website/Materials and — absent **prior written approval** —
  prohibit (a) data-gathering/extraction tools against pathofexile.com,
  (b) **framing techniques enclosing the Website's contents** (⚠ our
  embedded Trade Site tab does exactly this to pathofexile.com), and
  (c) automated software/bots against the Website/Services, with the
  registered developer API as the sanctioned exception. The framing
  clause covers pathofexile.com only — it says nothing about embedding
  craftofexile.com / filterblade.xyz.
  [ToU](https://www.pathofexile.com/legal/terms-of-use-and-privacy-policy) ·
  [dev docs](https://www.pathofexile.com/developer/docs)

**What this means for a FREE Kalandra (the active plan):**

1. **Bundling the scraped knowledge base is broadly permitted.** CC
   BY-NC-SA's NonCommercial clause targets uses "primarily intended for
   commercial advantage or monetary compensation" — a free community tool
   is the standard permitted case. Compliance obligations we DO take on:
   **attribution + license notice** (credit poe2db/poe2wiki and surface
   the CC BY-NC-SA notice in the app's About/credits and the README —
   new gating row), and ShareAlike applies to the *data*, which is fine
   since we redistribute it as-is in the DB, not relicensed.
2. **GGG's ToS clauses apply regardless of price** — the scraping and
   framing prohibitions are about pathofexile.com access, not money. Two
   asks in one email to GGG: blessing for the read-only scrape/embed
   patterns, and OAuth client registration (§3). Until answered, the embedded Trade
   Site tab is tolerated-risk (the ecosystem precedent: GGG has left
   similar tools alone for years) — an "open in browser" fallback exists
   if they object.
3. **One residual gray zone:** if the project's circumstances ever
   changed (any commercial turn), the CC-NC data is not an asset that
   transfers — the pipeline matrix in the vision doc exists so data
   sources can be replaced cleanly if that day ever comes. A counsel
   question for then, not now.
4. Game-file extraction (`dat_parser`/`oodle_extractor`) remains
   strategically prime — the eventual replacement for scraping entirely,
   and the most licensing-clean source there is (the user's own install).
5. **Unverified residue:** poe.ninja's API terms and craftofexile/
   filterblade embedding policies produced no verifiable claims — treat
   as unknown; a friendly email to each (all small teams) settles it.

**Appendix — if a PAID build ever happens:** the analysis flips back:
NC bars bundling the scraped DB (ship scraper-not-data, or game-file
extraction only), the Trade Site embed needs written approval, and
counsel review becomes mandatory. Keep this paragraph; don't relearn it.

## 3. Trade API automation: allowed, but only in the OAuth lane

**Verified (all 3–0):**

- **No fixed numeric rate limits exist.** Limits are dynamic, delivered
  per-response via `X-Rate-Limit-Policy` / `-Rules` / `-{rule}`
  (`max:period:lockout`, e.g. `20:5:60`) / `-{rule}-State` /
  `Retry-After` — clients are **required to parse and obey them**;
  frequent violations get application access revoked, and bursts of 4xx
  responses also trigger restrictions.
  [dev docs](https://www.pathofexile.com/developer/docs) ·
  [Novynn header spec](https://www.pathofexile.com/forum/view-thread/2079853)
- **OAuth 2.1 is the sanctioned lane**: registration for private data,
  desktop apps = public clients restricted to **PKCE** flows, **no
  credentials embedded in distributed binaries**, and a mandatory
  User-Agent of the form `OAuth {clientId}/{version} (contact: {email})`.
  [authorization docs](https://www.pathofexile.com/developer/docs/authorization)

**What this means for W3-22 (scheduled searches + notifications):** build
it on a **registered OAuth client with per-user PKCE** (we already have
`core_engine/oauth_pkce.py` from the GGG-OAuth work) with a rate-limit
governor that parses the X-Rate-Limit headers — never POESESSID, never an
embedded shared secret, never blind interval polling. **Unverified
residue:** whether the livesearch websocket specifically is inside the
sanctioned lane, and what precedent tolerated tools (Awakened PoE Trade /
Exiled Exchange 2 / Sidekick, which historically use POESESSID) actually
establish — no claims survived; ask GGG when registering the client.

## Action list distilled (rev 2 — free-forever plan)

| # | Action | Owner | Cost |
|---|---|---|---|
| 1 | Add data attribution + CC BY-NC-SA license notices (About/credits UI, README, installer) — our actual compliance obligation as a free distributor | Feature Worker | — |
| 2 | Email GGG once: read-only scrape/embed blessing + OAuth client registration | Christian | — |
| 3 | Optional but recommended for adoption: Azure Artifact Signing (individual, US) wired into the release script — kills the SmartScreen wall | Christian + Feature Worker | ~$10/mo |
| 4 | Email poe.ninja / Craft of Exile / FilterBlade: friendly heads-up + embedding OK-check | Christian | — |
| 5 | Build W3-22 notifications ONLY on registered OAuth + PKCE + header-governed rate limiting (never POESESSID) | Feature Worker | — |
| 6 | Keep Game-File R&D priority high — eventual scrape replacement, cleanest source | routines | — |
| 7 | (Dormant) If a paid build ever happens: apply the appendix — scraper-not-data, embed approval, counsel | — | counsel |

## Refuted during verification (excluded above)

- "Trusted Signing open to individuals since late 2024" — refuted 1–2:
  onboarding was paused April 2025; the current-state framing above is
  what survived.
- "poe2db.tw/privacy contains no licensing signal" — refuted 1–2: the
  site's disclaimer/footer do carry the CC BY-NC-SA notice.
