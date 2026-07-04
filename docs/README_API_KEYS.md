# Kalandra Overlay — Getting an AI API Key (the "brain" for the talking Divine Orb)

The Divine Orb can listen to you (local, on your PC), think (a cloud AI), and
speak back (local, on your PC). The **thinking** part needs an API key from one
AI provider. You only need **one** of the two below.

An "API key" is just a long secret password that lets the app talk to the AI on
your behalf. Usage is pay-as-you-go and usually costs a few cents; both providers
give you a free trial credit to start. **Never share your key** — treat it like a
password. In this app it's stored in your Windows Credential Manager, not in plain
text.

You can paste your key in the overlay: click the **bottom-right blue medallion →
Settings**, find **OpenAI** or **Google Gemini**, paste the key, click **Save**.
The Settings panel also has **"Get a key"** buttons that open the right page for you.

---

## Option A — OpenAI (ChatGPT)

1. Go to https://platform.openai.com/api-keys
2. Sign in (or create an account).
3. Click **"Create new secret key"**, give it a name like `Kalandra`.
4. Copy the key (it starts with `sk-...`). **You can only see it once** — copy it now.
5. Add a payment method / credits under **Billing** if prompted.
6. In the overlay: Settings → **OpenAI / ChatGPT** → paste → **Save**.
7. In Settings, set the **AI brain** dropdown to **openai**.

## Option B — Google Gemini

1. Go to https://aistudio.google.com/app/apikey
2. Sign in with a Google account.
3. Click **"Create API key"**.
4. Copy the key.
5. In the overlay: Settings → **Google Gemini** → paste → **Save**.
6. In Settings, set the **AI brain** dropdown to **gemini**.

---

## Which should I pick?

- **OpenAI** tends to give the most natural answers; great default.
- **Gemini** has a generous free tier and is a good no/low-cost option.

Either way, the app grounds the AI's answers in your locally-scraped PoE2 database,
so the Orb's replies are about the actual game data you've synced — not guesses.

## Costs / safety

- You are billed by your AI provider, not by this app. Set a monthly spend limit
  in their billing dashboard if you want a hard cap.
- If you ever think your key leaked, delete it on the provider page and create a
  new one; then update it in Settings.
