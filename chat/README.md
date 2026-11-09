# Ask the mission: the explorer's chatbot

A small chatbot on the explorer page. It answers technical questions using only this project's own content, and each answer cites its sources. Questions it can't answer from that content get a polite no and a suggestion.

```
browser (site/index.html)  --POST /chat-->  Cloudflare Worker (chat/worker)  -->  Claude Haiku 5.5
                                              |  BM25 search over corpus.json (61 chunks)
                                              |  the top 8 chunks go to Claude as citable documents
```

- **What it knows:** the page text, `site/data.json` written out as one fact sheet per day plus mission totals, the README, and both notebooks. `build_corpus.py` turns all of that into `worker/src/corpus.json`.
- **How the key stays safe:** the Claude API key exists only on the Worker, as a secret. The page never sees it.
- **How the Worker is protected:**
  - It only accepts requests from the origins listed in `ALLOWED_ORIGINS`.
  - Each visitor IP gets 8 questions a minute, and the whole site gets 40 a minute.
  - Questions are capped at 400 characters.
  - Questions that share no words with the corpus are declined without calling Claude.

## Run it on your computer

You need [Node.js](https://nodejs.org) 20 or newer and an Anthropic API key from [console.anthropic.com](https://console.anthropic.com).

**1. Install the Worker's packages:**

```bash
cd chat/worker && npm install
```

**2. Give the Worker your key.**

Create a file named `chat/worker/.dev.vars` containing this one line:

```
ANTHROPIC_API_KEY=sk-ant-...your key...
```

`.dev.vars` is git-ignored. Never put the key in `wrangler.toml` or in the page.

**3. Start the Worker** (it listens on port 8787):

```bash
cd chat/worker && npm run dev
```

**4. Serve the page** from a second terminal:

```bash
python3 -m http.server 8765 --directory site
```

**5. Open the page.**

Go to http://localhost:8765. A round gold button appears at the bottom right. It only appears when the page knows a chat address; on `localhost` it uses `http://localhost:8787/chat`.

Use port 8765 for the page, because it is the local origin the Worker allows. To use another port, add it to `ALLOWED_ORIGINS` in `wrangler.toml`.

## Test it

Retrieval tests are offline, free, and need no key:

```bash
cd chat/worker && npm test
```

To try a question by hand while `npm run dev` is running:

```bash
curl -s localhost:8787/chat -H 'Origin: http://localhost:8765' -H 'Content-Type: application/json' -d '{"question":"What was the hottest soil temperature?"}'
```

`test/questions.js` lists the sample questions and the facts each answer should contain.

## Put it online (Cloudflare, free plan)

Do this once. It takes about ten minutes.

**1. Make a Cloudflare account.**

Go to [dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up) and sign up. The free plan is enough.

**2. Log in from the terminal.**

```bash
cd chat/worker && npx wrangler login
```

A browser tab opens. Click **Allow**.

**3. Store your key as a secret.**

```bash
npx wrangler secret put ANTHROPIC_API_KEY
```

Paste the key when it asks. Cloudflare encrypts it, and it never appears in the code.

**4. Deploy:**

```bash
npm run deploy
```

At the end it prints an address like `https://chandrayaan3-days-chat.<your-name>.workers.dev`.

**5. Point the page at it.**

In `site/index.html`, find `const CHAT_API` and put that address, followed by `/chat`, where the empty `""` is:

```js
const CHAT_API = location.hostname === "localhost" ? "http://localhost:8787/chat" : "https://chandrayaan3-days-chat.<your-name>.workers.dev/chat";
```

Push to `main`, and GitHub Pages republishes the page with the chat button.

**6. If your site lives somewhere other than `madhavsomanath.github.io`,** add that origin to `ALLOWED_ORIGINS` in `wrangler.toml`, then run `npm run deploy` again.

**7. Set a spending limit.**

Give this chat its own key, so a problem with it can't touch your other projects:

1. In the Anthropic console, create a workspace just for this chat.
2. Set a monthly spend limit on that workspace, for example $5.
3. Create the API key inside that workspace and use it in step 3.

If you already stored a key from another workspace, run step 3 again with the new key.

The Worker's checks stop browsers on other sites from using your chat. They can't stop someone running a script that fakes the page's address. The rate limit slows such a script down, and the spending limit is what caps the bill. Each answer costs about a tenth of a cent with Haiku.

## When the project's content changes

Rebuild the corpus, test it, and redeploy:

```bash
python3 chat/build_corpus.py
cd chat/worker && npm test && npm run deploy
```

## Data use

The corpus holds only values derived from the archive, the same ones `site/data.json` already publishes, and never raw files. Questions and the matching excerpts are sent to Anthropic's API to write each answer, and the page tells visitors so.
