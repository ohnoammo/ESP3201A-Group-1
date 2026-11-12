# Design choices (Codex build)

Every choice that section 4 of `CODEX_README.md` leaves open, as implemented in `codex_steer.py`. This is
activation steering: no weights change, and it is not reinforcement learning or fine-tuning.

All "deterministic orders" below sort by `SHA-256("codex-<tag>:<question id>")`, with tag `fold`, `order`,
`inner`, `smoke` or `blind`. Nothing uses a random-number generator except the smoke test's fixed test
direction (torch seed 0).

## Data and files

- **Reuse of the Exp 2 script.** `prompts`, contexts, scoring and citation stripping are imported from
  `exp2_gitlab_scale.py` (`sympy_prompt`, `pool_docs`, `chunk_set`, `pack`, `format_context`, `short_id`,
  `covered`, `auto`, `abstained_strict`, `hedged`, `strip_citations`, `_candidates`, `longest_shared_run`,
  `words`, `read_jsonl`, constants). Nothing is copied, so prompts match the stored run byte for byte.
  The script changes the working directory to the repo (its paths are relative) and sets
  `sys.dont_write_bytecode`, so it writes nothing into James's repo except its own folder.
- **Symlinks.** Every file in the extracted `gitlab_runner_copy` on Clifton's PC is a Windows symlink. All of
  them resolved and read correctly, so `ESP3201A_SWE_exp1_app\` was not needed.
- **Prompt file.** `prompts.jsonl` stores the full system and user text, so the GPU steps never rebuild
  contexts. On James's machine `prepare` rebuilds everything and must produce files identical (line endings
  ignored) to the copies shipped in `out/`; any difference stops the run.
- **Input hashes.** `expected_hashes.json` holds SHA-256 of the 14 code and data files the experiment reads
  and one combined hash over all 2,231 pool MR files (SHA-256 of the lines `"<MR> <sha256>\n"` in MR order).
  `make-hashes` produced it from the `Latest` copy.

## Prompts

- **Twin exclusion.** Own MR plus the question's `quote_elsewhere` MRs plus its `exclude_prs` (the same rule
  that built the `removed` questions). For all 52 answerables this is only the own MR.
- **`span_in_context`.** `covered()` on the packed chunks, as in `cmd_generate`; "span in context" means
  `any` (47 of 52), which is the count the README expects. 46 have `all`.

## Pairs

- **Unanswerable rejection, stored.** Used when the stored F0 response is neither a strict abstention nor
  empty after removing citations: 5 questions (`rm3846`, `nr3177`, `nr1781`, `nr3805`, `nr4460`). The text is
  used as stored (stripped of outer whitespace), citations included.
- **WHAT-as-WHY wording.** `Because the merge request "<title>" made this change. [<cite>]`. The title comes
  from the saved MR JSON (`load_pr`); a leading `Draft:` or `WIP:` and a trailing full stop are removed;
  nothing else changes. I kept the README's form because a quoted title stays grammatical for every title
  (an earlier `This change was made to <title>` read badly for titles like "Changed symbol in docs table").
- **Citations.**
  - Grounding chosen (both `g_nf` and `g_what`): the first chunk in context order that fully contains a gold
    quote (`gold_chunks_fixed_s512_o77`); if none is in context, the first in-context overlapping chunk
    (`overlap_chunks_…`). In practice every one of the 47 had a containing chunk.
  - `g_what` rejected cites the **same** gold chunk as the chosen answer, so the pair differs in content
    (reason vs restated change) and not in the citation.
  - `twin` rejected: gold answer + the top-ranked chunk of the twin context (an answer without its evidence).
  - `unans` WHAT-as-WHY rejected: the highest-ranked in-context chunk of the question's own MR (no_reason
    questions), else the top context chunk (removed questions, whose MR is excluded).
  - Citation format: `<answer> [PR1234-c0]`, one space before the bracket, as the v3 prompt asks.
- **Pair ids.** `unans:<id>`, `twin:<id>`, `g_nf:<id>`, `g_what:<id>`.

## Folds, ratios, inner sets

- **Folds.** Four strata in this order: answerable with span in context (47), answerable without (5),
  no_reason (8), removed (10). Within a stratum, ids are sorted by `SHA-256("codex-fold:<id>")` and dealt
  round-robin to folds 0–4, with the pointer carried across strata so fold sizes balance. Result: 14
  questions per fold. Stratifying the answerables by span-in-context is finer than "by type" and keeps the
  grounding pairs per fold even (9 or 10).
- **Ratio subset order.** Within each family, each `how` group is sorted by `SHA-256("codex-order:<id>")`
  and the groups are merged by position fraction (i + ½) / n, ties by `how` name. Any prefix therefore keeps
  the groups' proportions (e.g. refusal: unanswerables and twins in their 14:42 proportion), and because both
  grounding groups use the same question order, the `g_nf` and `g_what` pairs of one question are taken
  together. The subset is the first a·m refusal and b·m grounding pairs, m = min(R // a, G // b), with
  (a, b) = (2, 3), (1, 1), (3, 2).
- **Inner set.** All training unanswerables (15 in folds 0–1, 14 in folds 2–4) plus the first 14 training
  answerables with span in context in `SHA-256("codex-inner:<id>")` order.

## Activations

- **Layers.** 14, 20, 25 are 0-based indices into `model.model.layers` (the 15th, 21st and 26th of 36
  blocks). The activation is that block's output hidden state, i.e. HF `output_hidden_states[L + 1]`.
- **Response-token mask.** prompt ids = `apply_chat_template([system, user], add_generation_prompt=True,
  tokenize=False)` tokenized with `add_special_tokens=False`; response ids = the response text tokenized
  separately with `add_special_tokens=False`. The input is prompt ids + response ids; the mask is positions
  `len(prompt) … end`. The closing `<|im_end|>` is **not** included. The CPU test checks that these ids are
  exactly a prefix of the chat template applied to the full conversation.
- **Positions.** The response token positions themselves (each position's output), not the positions that
  predict them.
- **Forward pass.** `model.model(...)` with `use_cache=False`; no LM head (saves ~1 GB of logits), and the
  pass stops after the last needed layer (an exception raised in the hook of layer 25).
- **Dtype.** The model runs in bf16. Layer outputs are cast to float32 before averaging; per-pair means are
  saved as float32 (`out/acts/*.npz`), differences and means are taken in float64, vectors stored as float32.
- **Norm sanity number.** `vector_info.json` gives each vector's L2 norm divided by the typical residual
  norm at that layer (mean per-token L2 norm at response positions over all pair passes), the cosine between
  the refusal-part and grounding-part vectors, and the minimum cosine between the 5 folds' vectors.

## Hook

- `register_forward_hook` on `model.model.layers[L]`; it returns a modified output (tuple or tensor).
- **Prefill vs decode.** The first call of a generation is the prefill: only position −1 (the last prompt
  token) gets `+ strength·v`. Every later call is a decode step with exactly one position, which gets
  `+ strength·v`; a decode call with more than one position raises an error. The number of hook calls must
  equal the number of new tokens, or the row is not written.
- **Precision.** The addition is done in float32 (`(h.float() + delta).to(bf16)`), then cast back.
- **Removal.** The handle is removed in a `finally` block; the smoke test checks no hook is left.
- Strength 0 never installs a hook (its answers are the baseline rows).

## Generation

- `model.generate(do_sample=False, temperature=None, top_p=None, top_k=None, max_new_tokens=512,
  use_cache=True)`, batch 1, attention mask all ones. The end tokens are the generation config's
  `eos_token_id` list plus the tokenizer's eos.
- `hit_max` = 512 new tokens and the last token is not an end token.
- The decoded text uses `skip_special_tokens=True`.

## Selection and degenerate test

- **Degenerate.** Any of: no Unicode letter; `hit_max`; one 4-gram of lower-cased `\w+` words occurring
  6 or more times anywhere in the text (not necessarily consecutively).
- **Drop rule.** degenerate count / inner size > 1/10, computed with exact fractions.
- **J** is computed with exact fractions; ties: smaller strength, then |layer − 20|, then smaller layer.
  Strength 0 has no layer and ranks first on the strength tie-break.
- **All dropped.** The fold is not steered and `all_settings_dropped` is recorded.

## Tests and sheet

- Exact McNemar: p = min(1, 2·P(X ≤ min(b, c))) with X ~ Binomial(b + c, ½); p = 1 when b + c = 0. Holm over
  the 9 p values.
- **Blind sheet.** Only answered answerable answers (a strict refusal has nothing to label). Answers are
  compared after `strip_citations`; identical text for the same question appears once, and the key lists
  every arm that gave it. Order: `SHA-256("codex-blind:<id>\n<text>")`. The key stores a SHA-256 of each
  answer so `stats` can detect an edited answer column.

## Runtime

- Every GPU step appends one JSON row per answer and skips keys already present; a half-written last line
  is cut off on restart. Rows are flushed at once and fsync'd every 20 rows.
- On Windows the GPU steps ask the OS not to sleep while they run (`SetThreadExecutionState`); this is a
  per-process request, not a settings change.
- Logs: `out/logs/<command>.log`.

## What I could and could not test

`tests\cpu_test.py`, run on Clifton's PC (no GPU) on 7 Nov; results in `tests\cpu_out\results_A.json` and
`results_B.json`. **All 38 checks passed** (12 in part A, whose first check is the real `smoke` command with
its own 9 checks, and 26 in part B). `smoke` then gained a mask-prefix check (2 more checks) and was re-run
on the small model: 11 of 11 passed. The same prefix check was also run with the real
`Qwen/Qwen3-4B-Instruct-2507` tokenizer (revision `cdbee75f17c0…` on 7 Nov; tokenizer files only) on 5 real
prompts of 2,828 to 3,306 tokens: all passed; the generation prompt ends `<|im_start|>assistant\n` with no
think tags.

**Part A, real model** (`Qwen/Qwen2.5-0.5B-Instruct`, float32, CPU, layers scaled to 9/13/17 of 24, 40 new
tokens, torch 2.15.0+cpu, transformers 5.22.2):
- The real `smoke` command passed all 9 checks: greedy output identical twice (2 prompts); a random
  direction changes both outputs; removing the hook restores both; no hook left behind; a zero vector
  through the hook gives the unsteered output; in prefill the position before the last is bit-identical
  and the last prompt position changes.
- Prompt ids + response ids are exactly a prefix of the chat template applied to the whole conversation,
  for a refusal and a gold answer (so the response mask is right).
- Activations for 4 real pairs (`unans:nr3177`, `twin:q3220`, `g_nf:q3220`, `g_what:q3220`) are finite and
  response-only; their mean difference at layer 13 has norm 0.17 × the typical residual norm.
- Steering 2 real prompts with that vector at strengths 0.5, 1, 2, 4: unsteered output restored afterwards,
  no hook left; strength 4 flipped `q3220` from a refusal to an answer, strengths up to 2 did not.

**Part B, fake model** (a deterministic stand-in for `generate` and `acts`, the full pipeline on all 70):
vectors (45), no held-out pair in any fold's vector subset, no held-out question in any inner set, exact
ratios, baseline crash after 30 rows then resume to exactly 70 rows, a half-written last line cut off,
select (3,834 inner answers), a looping setting dropped as degenerate everywhere, tie-break, test (210 rows,
each with its own fold's setting), stats, blind sheet (deterministic on re-run), labels → correctness
stats, report, sweep (630 rows), and hand-checked McNemar, Holm and degenerate values.

**Also checked:** `prepare` run twice reproduces all 7 outputs byte for byte (the check James's machine
will run); `run_codex.ps1` parses without errors in Windows PowerShell 5.1.

**Not tested (needs James's machine):**
- the 4B model in bf16 on CUDA, the sm_120 / CUDA 12.8 build check, VRAM use and real run time;
- `preflight` on a GPU, including the model download and revision record (here only `make-hashes` ran);
- whether HF greedy decoding in bf16 is repeatable on the RTX 5070 (smoke checks it first);
- `run_codex.ps1` end to end, including its `git commit` steps and the zip;
- anything about whether steering helps: the fake model says nothing about that, and the small model's
  outputs are only a demonstration that the hook acts.

## Folders I was told not to open

I did not open `Latest\FOR_JAMES_steering\`, `Latest\steer_check\`, any `steer\` folder or any `keys\`
folder. Listing `exp2_gitlab_A2000\` showed the name `keys` in the directory listing; I did not list or
read inside it.

## Who built this

This "Codex" build was written by Claude (Opus 5.5) at Clifton's request, following `CODEX_README.md`
without looking at Claude's other build. See `protocol_issues.md`, item 1, for what that means for the
cross-check.
