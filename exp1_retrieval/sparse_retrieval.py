"""BM25 (sparse) retrieval in Qdrant, with a code-aware tokenizer.

Same shape as before (build_index / search_sparse, sparse vector "bm25", Modifier.IDF), but
the term-frequency vectors are now built by us instead of FastEmbed's Qdrant/bm25 (which uses
an English stemmer + stopword list and would mangle code identifiers).

Code-aware tokenizer (code_tokenize):
  - identifiers (camelCase, snake_case, dotted.names, letters+digits): keep the full
    identifier lowercased AND its parts:  getUserById -> getuserbyid, get, user, by, id
    django.db.models -> django.db.models, django, db, models.  No stemming on identifiers.
  - ordinary words: lowercased + English Snowball stemming (changes -> chang)
  - numbers with >= 2 digits are kept (issue / ticket numbers)
  - minimal stopword list; Python-ish words like if, for, not, none, in, is, and, or are KEPT
  - single characters are dropped

BM25 (Robertson & Zaragoza):
  score(q, d) = sum over query terms t of  qtf(t) * IDF(t) * tf*(k1+1) / (tf + k1*(1-b+b*|d|/avgdl))
  - the tf part is computed here (k1, b configurable; avgdl = mean chunk length in THIS
    collection) and stored as the sparse vector value;
  - IDF is applied by Qdrant at query time (Modifier.IDF), over the WHOLE collection
    (also when a date-window filter is used);
  - query vector values = how often each term occurs in the query (qtf), as in rank_bm25.
Check: python sparse_retrieval.py --selftest  (compares Qdrant scores with a plain-Python BM25
using the same formula, and the ranking with rank_bm25).
"""
import math
import re
import uuid
from collections import Counter
from functools import lru_cache

from qdrant_client import QdrantClient, models

PAYLOAD_KEYS = ("chunk_id", "paper_id", "pr_number", "chunk_type", "file_path",
                "created_ts", "text", "start", "end")


def to_point_id(chunk_id):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))   # same id string -> same UUID


def payload(c):
    return {k: c.get(k) for k in PAYLOAD_KEYS}


# ---------- 1. Code-aware tokenizer ----------
STOPWORDS = frozenset("""a an the of to at on by be been being are was were am this that these
those it its i we you he she they our your their my me us them so than there here also just
very can could would should will do does did has have had which who whom what when where
""".split())

_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*|\d+")
_CAMEL = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")


@lru_cache(maxsize=None)
def _stem(word):
    return _stemmer().stem(word)


@lru_cache(maxsize=1)
def _stemmer():
    from nltk.stem.snowball import SnowballStemmer
    return SnowballStemmer("english")


def code_tokenize(text):
    out = []
    for m in _WORD.finditer(text):
        w = m.group()
        if w.isdigit():
            if len(w) >= 2:
                out.append(w)
            continue
        parts = [p for seg in re.split(r"[._]+", w) if seg for p in _CAMEL.findall(seg)]
        if len(parts) > 1 or "_" in w or "." in w:          # identifier: full + parts, no stem
            full = w.lower().strip("._")
            if len(full) >= 2:
                out.append(full)
            out.extend(p.lower() for p in parts if len(p) >= 2 and p.lower() != full)
        else:                                               # ordinary word: stopwords + stem
            lw = w.lower()
            if len(lw) >= 2 and lw not in STOPWORDS:
                out.append(_stem(lw))
    return out


# ---------- 2. BM25 encoder (term-frequency side) ----------
class CodeBM25Encoder:
    """Fit on one collection's chunk texts (vocabulary + avgdl), then turn texts into sparse
    vectors. Vocabulary ids are exact (no hashing, so no collisions)."""
    name = "code"

    def __init__(self, k1=1.2, b=0.75, tokenize=code_tokenize):
        self.k1, self.b, self.tokenize = k1, b, tokenize
        self.vocab, self.avgdl = {}, 1.0

    def fit(self, texts):
        lengths = []
        for t in texts:
            toks = self.tokenize(t)
            lengths.append(len(toks))
            for tok in toks:
                self.vocab.setdefault(tok, len(self.vocab))
        self.avgdl = sum(lengths) / max(1, len(lengths)) or 1.0
        return self

    def doc_vector(self, text):
        tf = Counter(self.tokenize(text))
        dl = sum(tf.values())
        norm = self.k1 * (1 - self.b + self.b * dl / self.avgdl)
        idx, val = [], []
        for tok, f in tf.items():
            if tok in self.vocab:
                idx.append(self.vocab[tok])
                val.append(f * (self.k1 + 1) / (f + norm))
        return idx, val

    def query_vector(self, text):
        qtf = Counter(t for t in self.tokenize(text) if t in self.vocab)
        return [self.vocab[t] for t in qtf], [float(c) for c in qtf.values()]


class FastEmbedBM25Encoder:
    """The previous approach (FastEmbed Qdrant/bm25: English stemming + stopwords), kept as
    an option for comparison."""
    name = "fastembed"

    def __init__(self, k1=1.2, b=0.75):
        self.k1, self.b, self.model = k1, b, None

    def fit(self, texts):
        from fastembed import SparseTextEmbedding
        avg = sum(len(t.split()) for t in texts) / max(1, len(texts))
        self.model = SparseTextEmbedding(model_name="Qdrant/bm25", k=self.k1, b=self.b,
                                         avg_len=avg)
        return self

    def doc_vector(self, text):
        e = next(self.model.embed([text]))
        return e.indices.tolist(), e.values.tolist()

    def query_vector(self, text):
        e = next(self.model.query_embed(text))
        return e.indices.tolist(), e.values.tolist()


def make_encoder(kind="code", k1=1.2, b=0.75):
    return (CodeBM25Encoder if kind == "code" else FastEmbedBM25Encoder)(k1=k1, b=b)


# ---------- 3. Collection + upsert ----------
def add_payload_indexes(client, collection):
    """Index the fields used in filters (speeds up a Qdrant server; local mode ignores it)."""
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")              # local mode: "has no effect" warning
        for name, kind in (("pr_number", models.PayloadSchemaType.INTEGER),
                           ("created_ts", models.PayloadSchemaType.FLOAT)):
            client.create_payload_index(collection, name, field_schema=kind)


def build_index(client, collection, chunks, encoder=None, batch_size=256):
    """chunks: dicts with at least chunk_id, text (+ the PAYLOAD_KEYS). Returns the fitted
    encoder (needed again for queries)."""
    encoder = (encoder or CodeBM25Encoder()).fit([c["text"] for c in chunks])
    if client.collection_exists(collection):
        client.delete_collection(collection)
    client.create_collection(
        collection_name=collection,
        vectors_config={},
        sparse_vectors_config={"bm25": models.SparseVectorParams(modifier=models.Modifier.IDF)},
    )
    add_payload_indexes(client, collection)
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        points = []
        for c in batch:
            idx, val = encoder.doc_vector(c["text"])
            points.append(models.PointStruct(
                id=to_point_id(c["chunk_id"]),
                vector={"bm25": models.SparseVector(indices=idx, values=val)},
                payload=payload(c)))
        client.upsert(collection_name=collection, points=points)
    return encoder


# ---------- 4. Search ----------
def date_window_filter(lo_ts, hi_ts):
    """Only chunks of PRs created in [lo_ts, hi_ts] (pool B)."""
    return models.Filter(must=[models.FieldCondition(
        key="created_ts", range=models.Range(gte=lo_ts, lte=hi_ts))])


def search_sparse(client, collection, encoder, query, k=5, qfilter=None):
    idx, val = encoder.query_vector(query)
    if not idx:
        return []
    hits = client.query_points(
        collection_name=collection,
        query=models.SparseVector(indices=idx, values=val),
        using="bm25", query_filter=qfilter, limit=k, with_payload=True,
    ).points
    return [h.payload | {"score": h.score} for h in hits]


# ---------- 5. Self-test ----------
def _reference_scores(encoder, texts, query):
    """Plain-Python BM25 with Qdrant's IDF: ln(1 + (N - n + 0.5) / (n + 0.5))."""
    docs = [Counter(encoder.tokenize(t)) for t in texts]
    N = len(docs)
    q = Counter(t for t in encoder.tokenize(query) if t in encoder.vocab)
    scores = []
    for tf in docs:
        dl = sum(tf.values())
        s = 0.0
        for t, qc in q.items():
            if tf[t]:
                n = sum(1 for d in docs if d[t])
                idf = math.log(1 + (N - n + 0.5) / (n + 0.5))
                s += qc * idf * tf[t] * (encoder.k1 + 1) / (
                    tf[t] + encoder.k1 * (1 - encoder.b + encoder.b * dl / encoder.avgdl))
        scores.append(s)
    return scores


SAMPLE = [
    "Title: Fixed #30000 -- Made QuerySet.getUserById() handle None.\nDescription:\nThe ORM crashed when user_id was None.",
    "File: django/db/models/query.py (modified)\n@@ -10,6 +10,8 @@ class QuerySet:\n-    def get_user(self, user_id):\n+    def get_user(self, user_id=None):\n+        if user_id is None:\n+            return None",
    "Review thread on django/db/models/query.py:\n@reviewer: Why not raise ValueError here instead of returning None?\n@author: Returning None matches the existing behaviour of get_or_none().",
    "Comment by @felixxm:\nThanks for the patch. Please add a regression test and a release note.",
    "File: docs/releases/4.2.txt (modified)\n@@ -1,3 +1,5 @@\n+* Fixed a crash in ``QuerySet.get_user()`` when ``user_id`` is ``None``.",
    "Title: Refs #29999 -- Optimized HTTPResponse streaming.\nDescription:\nStreamingHttpResponse now uses a smaller buffer.",
]


def selftest():
    print("Tokenizer examples:")
    for s in ["getUserById", "user_id", "django.db.models", "HTTPResponse", "if x is not None:",
              "Fixed #30000 -- crashes when changing the dates"]:
        print(f"  {s!r:<45} -> {code_tokenize(s)}")
    client = QdrantClient(":memory:")
    chunks = [{"chunk_id": f"c{i}", "paper_id": str(i), "pr_number": i, "text": t,
               "created_ts": float(i), "start": 0, "end": len(t)} for i, t in enumerate(SAMPLE)]
    enc = build_index(client, "selftest", chunks, CodeBM25Encoder())
    from rank_bm25 import BM25Okapi
    okapi = BM25Okapi([code_tokenize(t) for t in SAMPLE], k1=enc.k1, b=enc.b)
    worst, agree = 0.0, 0
    queries = ["QuerySet get_user crashes when user_id is None",
               "why return None instead of raising ValueError",
               "HttpResponse streaming buffer", "regression test release note"]
    for q in queries:
        got = {int(h["chunk_id"][1:]): h["score"]
               for h in search_sparse(client, "selftest", enc, q, k=len(SAMPLE))}
        ref = _reference_scores(enc, SAMPLE, q)
        worst = max(worst, max(abs(got.get(i, 0.0) - r) for i, r in enumerate(ref)))
        top_q = max(got, key=got.get)
        ok = okapi.get_scores(code_tokenize(q))
        top_r = max(range(len(SAMPLE)), key=lambda i: ok[i])
        agree += top_q == top_r
        print(f"  query {q!r}: Qdrant top = chunk {top_q}, rank_bm25 top = chunk {top_r}")
    print(f"Max |Qdrant - reference BM25| score difference: {worst:.2e} "
          f"({'OK' if worst < 1e-3 else 'MISMATCH'})")
    print(f"Top result agrees with rank_bm25 on {agree}/{len(queries)} queries "
          f"(rank_bm25 uses a slightly different IDF, so small differences are possible)")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        selftest()
