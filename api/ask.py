"""
Groundcheck RAG endpoint.

Retrieval: lightweight hand-rolled TF-IDF + cosine similarity over the demo
dataset (api/data/posts.json). No heavy ML deps -> fast cold starts on Vercel.

Generation: Claude synthesizes a grounded verdict, citing only the retrieved
posts by id. The prompt forces JSON-only output so the frontend can render
structured cards instead of free text.

Swap-in path for real data: replace `load_posts()` with a call to your Reddit
data source (official API, or a third-party provider -- see README) and keep
everything downstream the same.
"""

import json
import math
import os
import re
from collections import Counter
from http.server import BaseHTTPRequestHandler

from anthropic import Anthropic

DATA_PATH = os.path.join(os.path.dirname(__file__), "data", "posts.json")
TOP_K = 6
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be",
    "to", "of", "in", "on", "for", "with", "that", "this", "it", "i", "you",
    "my", "me", "at", "as", "if", "would", "will", "just", "so", "not",
    "have", "has", "had", "do", "does", "did", "can", "could", "than",
    "then", "into", "over", "your", "their", "them", "from", "by", "about",
}


def tokenize(text):
    words = re.findall(r"[a-z']+", text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def load_posts():
    with open(DATA_PATH, "r") as f:
        return json.load(f)


def build_corpus(posts):
    docs = [tokenize(p["title"] + " " + p["text"]) for p in posts]
    df = Counter()
    for doc in docs:
        for term in set(doc):
            df[term] += 1
    n_docs = len(docs)
    idf = {term: math.log((n_docs + 1) / (freq + 1)) + 1 for term, freq in df.items()}

    def vectorize(tokens):
        tf = Counter(tokens)
        return {term: tf[term] * idf.get(term, 0.0) for term in tf}

    doc_vecs = [vectorize(doc) for doc in docs]
    return doc_vecs, idf, vectorize


def cosine(vec_a, vec_b):
    common = set(vec_a) & set(vec_b)
    dot = sum(vec_a[t] * vec_b[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values())) or 1e-9
    norm_b = math.sqrt(sum(v * v for v in vec_b.values())) or 1e-9
    return dot / (norm_a * norm_b)


def retrieve(query, posts, doc_vecs, vectorize, k=TOP_K):
    q_vec = vectorize(tokenize(query))
    scored = [(cosine(q_vec, doc_vecs[i]), i) for i in range(len(posts))]
    scored.sort(reverse=True)
    results = [posts[i] for score, i in scored[:k] if score > 0]
    if not results:
        results = posts[:k]
    return results


SYSTEM_PROMPT = """You are Groundcheck's analysis engine. You validate startup \
ideas using ONLY the community evidence provided to you -- never your own \
opinion of the market, and never facts outside the given evidence.

Rules:
- Every claim must trace back to one of the provided post ids.
- Never invent a quote. Paraphrase in your own words; do not copy sentences verbatim.
- If the evidence is thin or off-topic for the idea, say so plainly instead of forcing a confident verdict.
- Output ONLY valid JSON, no markdown fences, no preamble, matching this exact shape:

{
  "verdict_score": <integer 1-10>,
  "verdict_label": "<one of: Strong Signal, Mixed Signal, Weak Signal, Insufficient Evidence>",
  "one_line_verdict": "<one sentence, plain language>",
  "sentiment": {"positive": <0-100 int>, "neutral": <0-100 int>, "negative": <0-100 int>},
  "themes": [
    {"theme": "<short theme name>", "summary": "<1-2 sentence paraphrase>", "post_ids": ["p001", "p002"]}
  ],
  "citations": [
    {"post_id": "p001", "paraphrase": "<one sentence, your own words, no quotes>"}
  ],
  "recommendation": "<2-3 sentences of concrete next step advice grounded in the evidence>"
}
"""


def call_claude(idea, evidence_posts):
    client = Anthropic()  # reads ANTHROPIC_API_KEY from env
    evidence_block = "\n\n".join(
        f"id: {p['id']}\nsubreddit: {p['subreddit']}\ntitle: {p['title']}\ntext: {p['text']}\nupvotes: {p['score']}"
        for p in evidence_posts
    )
    user_prompt = f"""Startup idea to validate: "{idea}"

Community evidence (demo dataset):
{evidence_block}

Return the JSON object now."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    return json.loads(text)


class handler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        self._send_json(405, {"error": "This endpoint only accepts POST requests with a JSON body: {\"idea\": \"...\"}"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw or b"{}")
            idea = (body.get("idea") or "").strip()

            if not idea:
                self._send_json(400, {"error": "Please describe the idea you want to validate."})
                return

            posts = load_posts()
            doc_vecs, idf, vectorize = build_corpus(posts)
            evidence = retrieve(idea, posts, doc_vecs, vectorize, k=TOP_K)

            if not os.environ.get("ANTHROPIC_API_KEY"):
                self._send_json(500, {
                    "error": "ANTHROPIC_API_KEY is not set in this deployment's environment variables."
                })
                return

            result = call_claude(idea, evidence)
            result["evidence"] = evidence
            self._send_json(200, result)

        except json.JSONDecodeError:
            self._send_json(400, {"error": "Malformed request body."})
        except Exception as e:  # noqa: BLE001
            self._send_json(500, {"error": f"Something went wrong: {str(e)}"})
