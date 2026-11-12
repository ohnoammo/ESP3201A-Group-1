# Judging instructions (Exp 2, test arms)

File: `codex_pack.csv`. Each row is one model answer to a "why" question about a Django pull
request. You see the question, the gold answer, the gold quotes (verbatim PR text that states the
reason) and the model answer. Model, prompt and retrieval condition are hidden; citation ids were
removed.

Fill `label` with exactly one of: correct / partial / wrong, and give a one-line `reason`.
- correct: states the reason the gold quotes support (paraphrase is fine; extra details are fine
  only if they do not contradict the PR).
- partial: gets part of the reason, or is in the right area but misses the key point (e.g. for
  the cookie-prefix question, saying such cookies are "HTTPS-only" without saying browsers ignore
  the Set-Cookie header counts as partial).
- wrong: a different or invented reason, or contradicts the gold.
Judge against the gold quotes, not against general knowledge. Do not change any other column.
