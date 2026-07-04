# Manual test checklist — 2026-07-03 build

Run Kalandra normally (`Kalandra.bat`), then work through these while playing
PoE2. Tick as you go; anything that fails → Issues tab (or tell the AI dev).

## A. Today's bug fixes

- [ ] **A1 — Double-click character selector (green medallion):** double-click
      it. ONLY the dashboard PoB tab should open — the character picker must
      NOT appear ~quarter second later. Try 5×, at different click speeds.
- [ ] **A2 — Single-click still works:** one click → character picker opens
      (after the brief 250 ms double-click window). No PoB tab.
- [ ] **A3 — Same test on the mic (top-left):** single = voice toggle,
      double = text chat, never both.
- [ ] **A4 — Same on the ruby (bottom-left):** single = snapshot,
      double = recording consent/start, never both.
- [ ] **A5 — Settings → Dashboard tabs:** every checkbox label clearly
      readable (light text), gold square when ticked.
- [ ] **A6 — Companion orb:** open the dropdown — orbs without art say
      "(no art yet)". Pick one → hint under the row turns amber and names the
      exact file to add. Drop any PNG at
      `gui_overlay/assets/orbs/2d/chance.png`, reopen Settings, pick Chance →
      overlay orb changes instantly and the hint turns green.

## B. Database sync (needs ~10 min idle)

- [ ] **B1:** Click the sync medallion. Let it run. In the terminal you should
      see poe2db finish, then (if poe2wiki is enabled in the DB updater) the
      wiki phase. If the wiki is blocking, you should see it STOP EARLY with a
      clear "30 consecutive failures... wait 10-15 minutes" message — not
      grind for an hour.
- [ ] **B2:** The finished dialog must show a real pending count (thousands —
      the failed wiki pages now count) instead of "Whole site covered ✅".
- [ ] **B3:** Re-sync 15 min later → pending should DROP as error pages retry.

## C. Accounts & buttons (Settings)

- [ ] **C1 — GGG "Test PoE2 API (no login)":** within a few seconds the status
      line should list the current PoE2 leagues. (In-game or out, any time.)
- [ ] **C2 — GGG "Connect GGG account":** with no client_id it must NOT error —
      it opens GGG's OAuth docs and explains the application-letter step.
- [ ] **C3 — Email row:** switch provider → "Open sign-in" and "Get app
      password" open the right pages for that provider.
- [ ] **C4 — Every link service** (poe.ninja, forums, PoB, FilterBlade,
      Exiled Exchange 2, Craft of Exile 2, Maxroll, Mobalytics, poe2wiki):
      "Open site" opens the right page.

## D. W3-01 theme (gold + gems)

- [ ] **D1 — Settings:** obsidian background, gold-bordered buttons that glow
      on hover, Save buttons emerald-tinted, Clear buttons ruby-tinted,
      "Connect GGG" sapphire, Done emerald. Nothing black-on-dark anywhere.
- [ ] **D2 — Dashboard:** selected tab has a gold top edge + gold text;
      scrollbars are thin gold rails; table headers gold-on-dark.
- [ ] **D3 — Dropdowns:** every combo box (AI brain, model, voice, orb, sync
      speed) opens a dark list with gold highlight — no white flash, no
      unreadable items.
- [ ] **D4 — While playing (true test):** alt-tab between the game and the
      dashboard for ~20 min of mapping. Watch for: white flashes on tab
      switches, unreadable text after Windows theme quirks, layout breakage at
      your resolution, GPU/CPU feel (theme should cost nothing — it's just
      styles).
- [ ] **D5 — Overlay unchanged:** the mirror/orb overlay itself should look
      exactly as before (W3-01 touches windows, not the medallion painting).

## E. Feature Wave 3 batch 2 (2026-07-03, later build)

- [ ] **E1 — YOUR frame, live (gate for the full rollout):** from
      `D:\GIT\Kalandra` run `python -m gui_overlay.kalandra_window`.
      The window is your Window.png with your three medallions top-right.
      Check:
      • the frame's celtic border renders crisply at any size — resize from
        tiny to fullscreen; corners must never stretch or blur (nine-slice);
      • medallions sit ON the top gold border (normal-window style),
        top-right: hover → colored glow ring + tooltip; red gem closes,
        green minimizes, blue maximizes; clicking them never triggers a
        resize, but the very top-right corner still resizes;
      • drag the gold border or the title strip to move (both monitors);
      • drag the outer rim (~10px) to resize from any edge/corner;
      • double-click the title strip = maximize/restore;
      • demo buttons open message dialogs wearing the same frame;
      • title text sits gold at top-left without touching the medallions.
      Report anything odd — Settings/dashboard migrate onto this chrome only
      after E1 passes.
- [ ] **E2 — Build tab toggle:** load a character, open Build (PoB). Click
      "View: Container ▣" / "View: Text ≡" — container shows stat chips, gear
      table, skill list with ★ on your main skill; text shows the classic
      dump. Restart Kalandra → your last view choice stuck.
- [ ] **E3 — Corrupted Blood check (your case):** in Container view the DPS
      chip comes from PoB's own PlayerStats — confirm it shows your real DoT
      numbers, not a poe.ninja-style zero. (Full configurable-damage-source
      view is W3-12, still queued.)
- [ ] **E4 — Live Search in-tab:** dashboard → Live Search → "Open here". The
      trade site should load INSIDE the tab (needs `pip install
      PyQt6-WebEngine`; without it you get a clean explainer card). Build a
      search, flip to Live, confirm the chime while you play.
- [ ] **E5 — GitHub wiring:** Settings → GitHub row → "Get a key" (token with
      repo scope) → Save. Dashboard → Issues: pick any entry → "Post selected
      → GitHub" → the status line shows the new issue URL; check it on
      github.com/castleism/Kalandra_Git. Then "Publish changelog → GitHub" →
      appears under Releases as a pre-release.

## F. Frame rollout (2026-07-03, latest build)

- [ ] **F1 — Settings:** open Settings (bottom-right medallion). It should be
      YOUR framed window: celtic border, medallions top-right, gold title on
      the band. Everything inside readable; scroll list works; resize from
      the rim; Done button closes.
- [ ] **F2 — Dashboard:** open from Settings or double-click the green
      medallion. Framed, resizable to any size, tabs gold-highlighted,
      maximize via blue medallion. Close (red gem) HIDES it (reopening is
      instant — same as before).
- [ ] **F3 — Chat:** double-click the mic medallion → framed chat window;
      typing and replies work as before.
- [ ] **F4 — Characters:** single-click the green medallion → framed picker;
      load a saved build → still loads and badges the selector.
- [ ] **F5 — Setup & Dependencies:** framed; install list scrolls; verify
      buttons work.
- [ ] **F6 — Message boxes:** finish a DB sync, save a recording, delete an
      issue, hit any error — the popups should all be small framed windows
      with emerald/ruby buttons, not grey Windows boxes.
- [ ] **F7 — While playing:** 20 min of mapping with alt-tabs. Watch for
      focus quirks, windows refusing to come forward, or anything that
      traps the cursor (report immediately if so — that's an instant fix
      priority).

## G. Feature Wave 3 batch 3 — trading & AI tools (latest build)

- [ ] **G1 — Ctrl+C price popup (THE in-game test):** while playing, hover any
      item and press Ctrl+C. A small dark-gold card should appear near your
      cursor: item name (rarity-colored), first mods, estimate line, and
      Trade ↗ / Price Check tab / ✕ buttons. It must NEVER steal focus from
      the game. Copy a Divine Orb → the estimate line should quote a real
      poe.ninja value (after one Exchange refresh or ~a minute for the cache).
      Copy gear → "No instant estimate" (we never invent prices). ESC or 12s
      dismisses. Toggle it off in Settings → confirm silence.
- [ ] **G2 — Crafting planner:** Crafting tab → "the absolute best
      quarterstaff for high phys and crit" → Plan craft. You should now get
      YOUR base recognized, phys+crit mod groups, and Routes A/B/C — with
      "(~X ex)" costs if you refreshed Exchange first. With an AI key set,
      the Orb's refinement appends below.
- [ ] **G3 — Currency tracker:** Exchange tab → right panel → enter your real
      counts (don't forget Gold) → Save holdings → Refresh prices → portfolio
      line shows Exalted + Divine value.
- [ ] **G4 — Daily movers:** after two days of at least one refresh each,
      "Today's market" lists ▲/▼ movers with buy/sell hints. (Day 1 says
      it's collecting history — expected.)
- [ ] **G5 — Saved searches:** Price Check → paste an item → Save search →
      name it → restart Kalandra → pick it from the dropdown → parses and
      opens correctly.
- [ ] **G6 — AI upgrade guide:** load your Corrupted Blood character → Build
      Sim → "Suggest upgrades (AI)" → numbered, build-specific suggestions
      (needs an AI key; without one it tells you so politely).
- [ ] **G7 — Reserve snapshots:** take a snapshot (ruby medallion) of an item
      → Reserve tab → it's first in the Snapshots dropdown → View snapshot
      opens it → copy the item in game → "Paste item from clipboard" → Save.

## H. Feature Wave 3 batch 4 (latest build)

- [ ] **H1 — Filter Editor, humanized:** load your filter. Every block should
      read as a sentence ("SHOW: Divine Orb · area >= 65") with a little
      color chip painted in ITS OWN label colors. Click a block → the plain
      description, then a live preview label that looks like the in-game
      drop text (colors/border/size from the filter), then the raw block.
      Show/Hide/Minimal are gem buttons; Save asks via a framed dialog.
- [ ] **H2 — Price Check insights:** paste a rare with a mixed mod pool. Each
      mod should be tiered (★ premium / ＋ good / — filler / ▼ downside) with
      advice, and a "Search strategy" verdict below. Sanity-check the tiers
      against your game sense — the tier table is data I can extend in
      minutes if anything reads wrong.
- [ ] **H3 — Character sheet:** load the Corrupted Blood character → Build
      tab → "Export sheet (HTML)". Browser opens a gold-themed page whose
      DPS chip shows your REAL DoT number (the poe.ninja lie, corrected).
      Share-test it: send the file to a friend, it's self-contained.

## I. UX round (latest build)

- [ ] **I1 — Checkboxes:** Settings → Dashboard tabs. ON = lighter square
      with a gold ✓; OFF = dark empty square. No more ambiguity.
- [ ] **I2 — One menu at a time:** open Settings → the overlay orb vanishes.
      From Settings click "Open Dashboard" → Settings closes, dashboard
      opens. Close the dashboard → the orb reappears.
- [ ] **I3 — Character picker height:** green medallion → picker opens tall
      (~940px); middle buttons no longer scrunched.
- [ ] **I4 — Tab toggles:** uncheck tabs in Settings, close Settings, reopen
      the dashboard → only checked tabs appear (rebuild is lazy now).
- [ ] **I5 — Visual gear view:** load a build → Build (PoB) tab → Container
      view shows the paperdoll: slots in PoB positions, rarity-colored
      frames, hover any card → full item description tooltip. Item ART
      appears within a few seconds per item on first view (fetched from
      poe2db, cached forever after — offline shows styled cards, no images).

## Reporting

Log failures in Dashboard → Issues tab with the checklist ID (e.g. "A1
double-click still opens both"). They'll flow to GitHub once W3-32 lands.
