# CI Log

Nightly build-audit / test-hardener run history. One entry per run: green
summaries get one line, failures get a full incident writeup. Keep this
file under ~200 lines — compact the oldest entries into a summary line
when it grows past that.

## 2026-07-10 — py_compile clean, 2 real test failures fixed, pip-audit blocked (environmental)

**py_compile**: all 70 `.py` files under `core_engine/`, `gui_overlay/`,
`tests/`, `scripts/`, and the repo root compiled clean (one pre-existing
`SyntaxWarning: invalid escape sequence '\P'` in `core_engine/pob_bridge.py:28`,
not a failure).

**Test suites — 2 real defects found and fixed:**

1. `tests/craft_checks.py` — "junk region fails soft" failed:
   `core_engine/craft_hunter.py:make_grabber()` did
   `{k: int(region[k]) for k in (...)}` with no guard, so a malformed
   region dict (missing keys, or non-numeric values like `{"left": "x"}`)
   raised instead of failing soft like the rest of the function's error
   paths. Fixed by wrapping the conversion in
   `try/except (KeyError, TypeError, ValueError): return None`. Re-ran:
   111 passed, 0 failed.

2. `tests/stress_test.py` — "is_connected falsey without keyring" failed,
   **and this test was polluting the real OS credential store**: the
   "account_manager — fail-closed without keyring" section never actually
   disabled keyring, so on any machine that has `keyring` installed (this
   one does — Windows Credential Manager backend), `set_secret("openai", "x")`
   wrote a real secret into `KalandraOverlay/openai`, and the next line
   read it back as truthy, failing the "falsey" assertion. Fixed by
   forcing `am._using_keyring = False` before exercising the no-keyring
   path, so the test exercises the fail-closed branch without touching
   the real keychain, and added an explicit `set_secret(...) is False`
   check. Also manually deleted the stray `KalandraOverlay/openai`
   credential this bug had written to the real Windows Credential Manager
   during earlier runs. Re-ran: 286 passed, 0 failed.

Both fixes committed with CHANGELOG entries. All other `tests/*_checks.py`
suites (companion, db_status, death, ghost, nerf, recorder, trade_query)
were green on first run, no changes needed.

**pip-audit — BLOCKED, environmental, not a code defect:**

`pip-audit -r requirements.txt` (installed fresh, wasn't present)
fails every dependency lookup against pypi.org with
`SSLCertVerificationError: unable to get local issuer certificate`.
Diagnosis: this machine's Avast antivirus does HTTPS traffic interception
(evidenced by `NODE_EXTRA_CA_CERTS=C:\ProgramData\Avast Software\Avast\wscert.pem`
and `SSLKEYLOGFILE=\\.\aswMonFltProxy\...` in the environment) — Avast
re-signs TLS connections with its own root CA, which is not present in
the `certifi` bundle that `pip-audit`'s `requests` session trusts. Plain
`pip install` succeeds (it appears to negotiate around this or use a
different trust path), but `requests`+`certifi` does not. This is a
local-machine trust-store gap, not a Kalandra dependency or code issue,
so I did not disable cert verification or otherwise paper over it.
**Recommended fix** (needs a human, out of scope for an autonomous run):
either export Avast's root cert into the certifi bundle pip-audit uses
(`certifi.where()` — append the Avast `wscert.pem` cert), or set
`REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` to a combined bundle that includes
it, or run pip-audit from a machine/CI runner without HTTPS-intercepting
AV. Dependency audit itself remains **not yet run** this cycle — retry
once the trust-store issue is resolved.

## 2026-07-10 — hardening pass

All green, +55 checks in new `tests/pob_sim_checks.py` (first coverage for
`core_engine/pob_sim.py`, 350 lines / 0 tests before this run) — found and
fixed a real NaN-crash in `stats_summary()` along the way.
