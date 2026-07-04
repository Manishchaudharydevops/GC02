# Groundcheck

A working RAG prototype: describe a startup idea, get a verdict grounded in
community evidence, with every claim traceable back to a specific cited post.

This is a **real, tested pipeline** — retrieval + LLM synthesis + a UI that
renders structured citations — running on a **synthetic demo dataset** of 30
Reddit-style posts (`api/data/posts.json`), because live Reddit access
requires a paid commercial API agreement (Reddit's official commercial tier
starts around $12,000/year) or a third-party data provider. Swapping in real
data is a small, isolated change — see "Going live with real data" below.

## Project structure

```
groundcheck/
├── public/              ← static frontend, served directly by Vercel's CDN
│   ├── index.html
│   ├── styles.css
│   └── script.js
├── api/
│   ├── ask.py           ← the RAG endpoint, POST /api/ask
│   └── data/posts.json  ← demo dataset
├── pyproject.toml       ← declares the Python entrypoint + dependencies
└── vercel.json
```

**Why `public/`:** Vercel's current Python runtime treats a declared
`pyproject.toml` entrypoint as a full application, not a scoped function —
so static files need to live in `public/` to be served by the CDN
independently of the Python app. Putting `index.html` at the project root
(an earlier mistake in this build) caused the root URL to be routed into
the Python handler instead, producing a 501 error on GET requests.

## How it works

1. **Retrieval** (`api/ask.py`) — a hand-rolled TF-IDF + cosine similarity
   search over the demo dataset. No heavy ML dependencies, so cold starts on
   Vercel stay fast.
2. **Generation** — the top-matching posts are handed to Claude with a system
   prompt that forbids inventing quotes or claims not present in the
   evidence, and forces structured JSON output (score, sentiment split,
   themes, citations, recommendation).
3. **Frontend** (`index.html` / `styles.css` / `script.js`) — plain HTML/CSS/JS,
   no build step, renders the JSON as a case-file style report.

## Run locally

```bash
pip install anthropic==0.40.0
export ANTHROPIC_API_KEY=sk-ant-...
npx vercel dev
```

Then open the printed local URL and submit an idea.

## Deploy to Vercel

```bash
npm i -g vercel
vercel
```

When prompted, or in the Vercel dashboard afterward, set the environment
variable:

- `ANTHROPIC_API_KEY` — your Anthropic API key (Settings → Environment Variables)

That's it — `vercel.json` already wires up the static frontend and the
Python function at `/api/ask`.

## Going live with real data

Everything downstream of retrieval is already source-agnostic. To point this
at real data instead of the demo dataset:

1. Replace `load_posts()` in `api/ask.py` with a call to your data source —
   Reddit's official Data API (commercial tier required for production use),
   or a third-party provider (Data365, Apify actors, etc. — cheaper than
   Reddit's direct commercial rate for most workloads, but check their terms).
2. Keep the same post shape: `{id, subreddit, title, text, score, author, url}`.
3. Consider caching retrieval results (e.g. Vercel KV or a Postgres +
   pgvector setup) once you're pulling from a live source, so you're not
   re-fetching and re-embedding on every request.
4. If your corpus grows past a few thousand posts, swap the hand-rolled
   TF-IDF for real embeddings (OpenAI/Voyage) + a vector DB — the TF-IDF
   approach here is intentionally lightweight for a small demo corpus, not
   built to scale to tens of thousands of documents.

## Notes on the current build

- The dataset is entirely synthetic — written to be representative of real
  discussion patterns, not scraped or copied from anywhere. Safe to ship,
  safe to look at, but it will only "know about" the ~30 topics seeded in
  `api/data/posts.json`. Ideas far outside those topics will get a low
  score or an "Insufficient Evidence" verdict — that's the system working
  correctly, not a bug.
- The system prompt explicitly disallows quoting verbatim and requires every
  claim to cite a post id, so you have a clean foundation for the "trust"
  requirements real users will expect (see the discussion in-chat about why
  generic AI opinions don't cut it anymore in this space).
