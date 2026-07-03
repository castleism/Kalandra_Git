# OAuth Client Registration Request — draft email to GGG

**Fill in the bracketed parts, then send to:** support@grindinggear.com
**Suggested subject:** Request to register an OAuth client (public/PKCE) for a personal, read-only PoE2 companion

---

To the Path of Exile API / Developer team,

My name is [YOUR NAME] (forum/account name: [YOUR ACCOUNT NAME]). I'm writing to
ask how I can register an OAuth 2.1 application, or to request a `client_id` for a
personal tool I'm building for Path of Exile 2.

I understand and respect that GGG does not encourage third-party tools, and I want
to be completely upfront about what this is and, just as importantly, what it is
not. The tool, "Kalandra," is a personal, single-user desktop companion that is
strictly **read-only and advisory**. It does not, and will not:

- automate any gameplay or send any input to the game client,
- read from or write to game memory, or interact with the running client in any way,
- provide any real-time mechanical advantage during play,
- operate at scale or on behalf of other users.

Everything it does is offline analysis the player could do by hand: it reads Path
of Building exports to display and explain a build, and presents publicly available
information. There is no botting, trading automation, or input simulation of any
kind, and I would be glad to comply with any conditions, rate limits, or review you
require.

What I would like to access, all for the authenticated user's **own** account and
read-only, is the minimal set of scopes:

- `account:profile` — to confirm the signed-in account.
- `account:leagues` — to list the player's current leagues.
- `account:characters` (realm `poe2`) — to read the user's own characters so the
  tool can display their build/stats. (The documentation indicates `GET /character`
  now supports `realm=poe2`.)
- `account:item_filter` — so the player can review and update **their own** loot
  filters from the app.

I intend to register as a **public client** using the Authorization Code grant with
PKCE and a localhost redirect, since this is a locally-installed desktop app with no
server component.

Could you let me know the correct process to obtain a `client_id` (the public docs
describe the OAuth flow but not the registration/approval step), and whether what I've
described is permissible? If a public client isn't appropriate for this use case, I'm
happy to follow whatever path you recommend, or to be told if it isn't currently
possible.

Thank you for your time, and for the work on the game.

Best regards,
[YOUR NAME]
[YOUR EMAIL]
[OPTIONAL: link to the project, e.g. your GitHub repo]

---

### Notes for you (not part of the email)

- The only published contact is `support@grindinggear.com`; there is no self-serve
  registration page, and these requests have historically gone unanswered, so set
  expectations low. It costs nothing to ask and to have a clean paper trail.
- Keep the tone exactly this compliant — GGG's stated concern is automation and
  unfair advantage, so leading with "read-only, no automation, no client
  interaction" is the whole pitch.
- If/when they grant a `client_id`, the OAuth (PKCE) flow is straightforward to add
  to Kalandra, and it would unlock real character sync and official filter editing.
  Until then, the offline-first versions (PoB import, local `.filter` editing) need
  no approval and stay fully ToS-clean.
