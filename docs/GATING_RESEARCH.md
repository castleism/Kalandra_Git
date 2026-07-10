# Gating Research — code signing, licensing, trade-API boundaries

*Researched 2026-07-10 via a 102-agent verified-research pass (5 search
angles, 20 sources fetched, 94 claims extracted, 25 adversarially verified:
23 confirmed / 2 refuted-and-excluded). Everything below cites primary
sources. This is research, not legal advice — the licensing section in
particular needs counsel before a commercial launch.*

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

**Recommendation:** sign with Artifact Signing Basic (~$120/yr) instead of
an OV/EV certificate. Wire `signtool` + the Trusted Signing dlib into
`scripts/make_release_zip.py`'s pipeline. **Unverified residue:** exact
2026 OV/EV price cards (SSL.com/Certum/Sectigo/DigiCert) and per-option
SmartScreen reputation behavior didn't survive verification — irrelevant
if we take the Azure path, revisit only if eligibility fails.

## 2. Licensing: the knowledge base is the blocker — and the strategy already contains the fix

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

**What this means for the two roadmaps:**

1. **The paid product cannot bundle the scraped knowledge base.** Options,
   best first: (a) **game-file extraction on the user's own install**
   (`dat_parser`/`oodle_extractor` path) — the user reads their own copy
   locally, nothing redistributed by us; this is already the post-GGG
   pipeline prototype, so the acquisition architecture and the licensing
   fix are the *same work* — priority of the Game-File R&D routine just
   went up. (b) User-initiated local scraping for personal use (ship the
   scraper, not the data — the NC license binds *our redistribution*, not
   what a user does personally; still gray, ask counsel). (c) Written
   permission from GGG/the wikis — the ToU's "without prior written
   approval" carve-out makes direct contact a real path, and it doubles
   as an acquisition conversation opener.
2. **The embedded Trade Site tab needs review before a paid release** —
   either GGG's written approval or degrade it to "open in browser" in
   the commercial build (the W3-21 prefilled URLs work either way).
3. Purely factual game numbers *may* be uncopyrightable in some
   jurisdictions — a narrowing argument, not a plan; counsel question.
4. **Unverified residue:** poe.ninja's commercial-API terms and
   craftofexile/filterblade embedding policies produced no verifiable
   claims — treat as unknown, ask the operators directly (all three are
   one-person/small teams that answer email).

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

## Action list distilled

| # | Action | Owner | Cost |
|---|---|---|---|
| 1 | Sign up for Azure Artifact Signing (individual, US); wire into release script | Christian + Feature Worker | ~$10/mo |
| 2 | Raise Game-File R&D routine priority — it's now the licensing fix AND the acquisition pipeline | routines | — |
| 3 | Commercial build plan: ship scraper-not-data; keep bundled DB for the free/personal build only, pending counsel | Christian | counsel |
| 4 | Email GGG: written-approval ask (bundled data, trade-site embed, OAuth client registration) — doubles as relationship opener for the acquisition thesis | Christian | — |
| 5 | Email poe.ninja / Craft of Exile / FilterBlade about commercial use + embedding | Christian | — |
| 6 | Build W3-22 notifications ONLY on registered OAuth + PKCE + header-governed rate limiting | Feature Worker | — |
| 7 | Degrade Trade Site tab to open-in-browser in any paid build until #4 answers | Feature Worker | — |

## Refuted during verification (excluded above)

- "Trusted Signing open to individuals since late 2024" — refuted 1–2:
  onboarding was paused April 2025; the current-state framing above is
  what survived.
- "poe2db.tw/privacy contains no licensing signal" — refuted 1–2: the
  site's disclaimer/footer do carry the CC BY-NC-SA notice.
