# Chunking + BM25 notes (Experiment 1, SWE-bench / Django PRs)

Run steps and all parameters are in `README.md`. This file explains the chunking and the
BM25 (sparse) side in more detail.

## PR document (`pr_document.py`)
One text per PR, always in this order: `Title:` + `Description:`, `Commit messages:`, one
block per changed file (`File: <path> (<status>)` + its diff), `Review thread on <path>:`
(root comment + replies, `@login: body`), `Comment by @login:` (conversation). Bots are
removed (GitHub `user.type == "Bot"`, logins ending in `[bot]`, small CI-bot list). Nothing
else is stripped. Every part is stored as a character span (`parts`), and so are all changed
lines (`changed_lines`) and every non-empty line (`line_spans`, the scoring units).

## Fixed-size chunking (`fixed_size_chunks`)
Windows of `size` tokens over the whole PR text, stepping by `size - overlap`. Ignores PR
structure (a window can start mid-hunk or span a comment and a diff). Untuned default 256
tokens, no overlap. "Tokens" = `\w+|[^\w\s]` (words + single symbols), same for every method.

## Structural chunking (`structural_chunks`), replaces semantic chunking
One chunk per part: title + description; commit messages; **each diff hunk** (chunk text is
prefixed with the `File: path` header so the path is searchable); each review thread; each
conversation comment. Never cuts across parts. A part over the **size cap** (default 512
tokens) is split at line breaks (`split_parts` in the results counts how often).
Why not semantic: it is sentence-based (built for prose); PRs are mostly diff lines and
already have explicit boundaries.
Structural chunks vary a lot in size (a 1-line hunk vs a long description), so the results
always report chunk-size stats (avg / median / p10 / p90 / max tokens), and `--size-matched`
adds a fixed-size run with the structural average size (no +-10% eligibility rule).

## BM25 (`sparse_retrieval.py`)
- **Code-aware tokenizer** (`code_tokenize`): identifiers (camelCase, snake_case,
  dotted.names) -> the full identifier lowercased + its parts (`getUserById` -> getuserbyid,
  get, user, by, id), not stemmed. Ordinary words -> lowercase + English Snowball stem.
  Numbers with >= 2 digits kept (ticket numbers). Minimal stopwords; `if, for, not, none, in,
  is, and, or` kept. Single characters dropped.
- **Own TF vectors**: value = `tf*(k1+1) / (tf + k1*(1-b+b*len/avglen))`, avglen per
  collection; vocabulary ids are exact (no hashing). Qdrant applies IDF
  (`Modifier.IDF`: `ln(1 + (N-n+0.5)/(n+0.5))`) over the whole collection. Query values =
  term counts in the query (as rank_bm25 does).
- **Check**: `python sparse_retrieval.py --selftest` -> Qdrant scores match a plain-Python
  BM25 to ~1e-7, and the top result matches `rank_bm25` on the sample queries.
- `--bm25 fastembed` switches back to the previous FastEmbed `Qdrant/bm25` encoder (English
  stemming + stopwords) as a comparison.
- Known trade-off: identifier parts are not stemmed but query words are, so "users" (query,
  -> user) matches the part `user`, while "running" (-> run) does not match a part `running`.
