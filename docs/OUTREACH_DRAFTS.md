# Outreach Drafts — ready to send

*Drafted 2026-07-10 per `docs/GATING_RESEARCH.md` action items #2 and #4.
Christian sends these from his own email; edit voice to taste. The GGG one
matters most — it's simultaneously the compliance ask, the OAuth
registration, and the first touch for the acquisition thesis. Verify the
current registration contact on pathofexile.com/developer/docs before
sending (it has been oauth@grindinggear.com).*

---

## 1. To Grinding Gear Games (developer/OAuth contact)

**Subject:** OAuth client registration + third-party tool blessing — Kalandra (free PoE2 overlay companion)

Hi GGG team,

I'm the developer of Kalandra, a free desktop companion app for Path of
Exile 2 (https://github.com/castleism/Kalandra_Git). Before going wider I
want to make sure everything we do sits inside your policies, and to
register properly for the API. Three things:

1. **OAuth client registration.** I'd like to register Kalandra as a
   public (desktop, PKCE-only) OAuth client per your developer docs.
   Intended scopes: reading a consenting user's own characters/stash for
   build advice, and trade search on the user's behalf with your
   X-Rate-Limit headers strictly obeyed. Client name: Kalandra; contact:
   christiancodyak@gmail.com; no credentials will ever be embedded in the
   distributed binary.

2. **Our design constraints, for the record.** Kalandra is read-only by
   hard rule: it never sends or intercepts game input, never automates
   any in-game action, and never reads game memory. It reads what the
   game shows the player (screen, clipboard on the player's own Ctrl+C,
   Client.txt). It is free, with no monetization.

3. **Two explicit permission asks under your Terms' "prior written
   approval" clause:** (a) the app currently embeds the official trade
   site in a webview so players use YOUR search UI rather than a
   replicated one — is that framing acceptable, or would you prefer we
   open the system browser? (b) the app's local knowledge base is built
   from community sites (poe2db, the community wiki); if you'd rather
   tools source game data some other way — official dumps, the API, or
   parsing the player's own installed files — we'll happily switch, and
   the app is already architected to swap data sources cleanly.

Happy to share anything else — full source is public. Thanks for the
game and for maintaining an API at all; very few studios bother.

Christian
(Kalandra — free PoE2 companion)

---

## 2. To poe.ninja (contact form / rasmuskl)

**Subject:** Kalandra (free PoE2 overlay) uses your public economy data — attribution + is this OK?

Hi Rasmus,

Kalandra is a free, open-repo PoE2 desktop companion
(https://github.com/castleism/Kalandra_Git). It pulls your public PoE2
currency overview (rate-limited, cached, descriptive User-Agent
identifying us) to show players economy snapshots and daily movers, and
it credits poe.ninja in the app and README. Two questions: is this usage
pattern fine with you, and is there anything you'd like us to change
(endpoint choice, cache duration, attribution wording)? Happy to adjust —
your site is load-bearing for the whole community and we don't want to be
a bad citizen. Thanks for everything you run.

Christian

---

## 3. To Craft of Exile / FilterBlade (template — send to each)

**Subject:** Kalandra (free PoE2 overlay) embeds [craftofexile.com /
filterblade.xyz] in an in-app browser tab — OK with you?

Hi,

Kalandra is a free PoE2 desktop companion
(https://github.com/castleism/Kalandra_Git). One of its dashboard tabs is
simply an embedded browser view of your site — full page, your ads and
branding untouched, nothing scraped or modified; it's just a convenience
so players keep your tool one tab away while playing. Wanted to check
that's OK with you, and whether you'd prefer anything different (a
particular landing URL, opening the system browser instead, a referral
tag). Credits to your site ship in the app's README. Thanks for the tool
— it's a permanent fixture of our players' workflow.

Christian

---

*After answers arrive: record outcomes in `docs/GATING_RESEARCH.md` and
flip the ROADMAP ToS row accordingly. If GGG answers on the trade-site
embed, the Feature Worker routine implements whichever mode they prefer.*
