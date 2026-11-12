# Codex rule: activation steering on the 70 GitLab Runner questions

Written 7 Nov 2026, before any GPU run. Commit this file before the first run and do not edit it after
results exist; add a dated note at the end instead.

**What this experiment is.** Activation steering (contrastive activation addition) on the frozen
`Qwen/Qwen3-4B-Instruct-2507`. A vector is added to the residual stream of one decoder layer while the model
generates. **No weights change. It is not reinforcement learning and not fine-tuning.** The professors asked
for "reinforcement learning of weight distribution in human checked 70 PRs"; this experiment uses the
checked set to build a steering vector instead, and the report must say so plainly.

**Status.** Exploratory, on the GitLab Runner transfer set, outside the Exp 2 Findings. Exp 2 itself
involved no learning.

Code: `codex_steer.py` (this folder). Open choices: `design_choices.md`. Problems with the protocol:
`protocol_issues.md`. Runbook: `README_CODEX_FOR_JAMES.md` + `run_codex.ps1`.

## Fixed inputs

| Item | Value |
|---|---|
| Questions | `exp2_gitlab_A2000/questions.jsonl`: 52 answerable, 8 no_reason, 10 removed |
| Contexts | Arm F0 as stored: fixed 512/77 chunks, dense top 100 from `candidates_fixed_s512_o77.jsonl`, alpha 0, budget 2,560, prompt v3 (sha1 of the GitLab Runner text from `sympy_prompt()`), built with `exp2_gitlab_scale.pack()` and `format_context()` |
| Context check | `prepare` stops unless all 70 rebuilt contexts equal `gen_F0.jsonl` in chunk ids, short ids and `span_in_context`. Result on Clifton's PC: 70/70 equal |
| Input hashes | `expected_hashes.json` (SHA-256 of 14 files plus a combined hash of the 2,231 pool MR files), from the `Latest` copy; `preflight` stops on any difference |
| Model | HF `Qwen/Qwen3-4B-Instruct-2507`, bf16, greedy, at most 512 new tokens, batch size 1. The revision is fixed by `preflight` in `out/model_revision.json` and written into every output row |
| Chat format | system message = v3 system text, user message = v3 user text with context and question, `add_generation_prompt=True` |
| Baseline | The same HF model with no hook. The stored Ollama rows are only a pipeline check (answer vs refuse agreement), never a baseline |

## Prompts

- **Main** (70): the F0 prompt of each question.
- **Twin** (52): each answerable question again, with its own MR (and any MR in its `quote_elsewhere`, none
  in practice) excluded, repacked from the same candidate list with the same budget. 0 of 52 twins needed an
  exclusion beyond the own MR.

## Pairs (script only; no human or LLM judgement)

Chosen = wanted behaviour, rejected = failure, on the same prompt.

| `how` | Family | Prompt | Chosen | Rejected | n |
|---|---|---|---|---|---|
| `unans` | refusal | main, each no_reason / removed | `Not found in the provided PRs` | stored F0 response if F0 answered (5); otherwise WHAT-as-WHY from the MR title (13) | 18 |
| `twin` | refusal | twin | `Not found in the provided PRs` | gold answer + `[top twin context chunk]` | 52 |
| `g_nf` | grounding | main, answerable with span in context | gold answer + `[gold chunk]` | `Not found in the provided PRs` | 47 |
| `g_what` | grounding | same | gold answer + `[gold chunk]` | WHAT-as-WHY from the MR title, citing the same gold chunk | 47 |

**After the human check: 159 pairs (5 dropped, 8 Nov, before any GPU run).** The table lists the 164 pairs as
built. After Clifton's check, 5 pairs are removed from every vector: `twin:q3239`, `twin:q1189`,
`twin:q1754`, `unans:nr3177` and `unans:nr4460`. The pairs actually used are `unans` 16 (3 stored F0 answers +
13 scripted), `twin` 49, `g_nf` 47 and `g_what` 47. The reasons are in `DROPPED_PAIRS` in `codex_steer.py`
and in `out/dropped_pairs.jsonl`. The 70 test questions are unchanged.

WHAT-as-WHY text: `Because the merge request "<title>" made this change. [<cite>]` (title with a leading
`Draft:`/`WIP:` and trailing full stop removed). The citation choices are in `design_choices.md`.

## Vector

- Activations: output of decoder layers **14, 20 and 25** (0-based index into `model.model.layers`; 36
  layers), averaged over the **response tokens only** (teacher forcing of prompt + response, no hook).
- Pair difference = mean(chosen) − mean(rejected); vector = mean difference over the pairs in use.
- One vector per fold × ratio × layer (45), from that fold's training pairs only.

## Applying it

strength × vector is added to the layer's output at the **last prompt position** (prefill) and at **every
generated position** (each decode step). Strength 0 means no hook. Removing the hook must restore the
unsteered output exactly (checked by `smoke`).

## Ratio

Refusal : grounding pairs among a fold's training pairs = **40:60, 50:50, 60:40**, i.e. exactly 2:3, 1:1,
3:2. The largest subset with that exact ratio is taken (m = min(R // a, G // b); a·m refusal and b·m
grounding pairs), as prefixes of a fixed deterministic order (see `design_choices.md`).

| Fold | Training refusal / grounding | 40:60 | 50:50 | 60:40 |
|---|---|---|---|---|
| 0, 1 | 56 / 74 | 48 / 72 | 56 / 56 | 54 / 36 |
| 2, 3, 4 | 56 / 76 | 50 / 75 | 56 / 56 | 54 / 36 |

## Folds

5 folds of 14 questions, stratified by type (answerable with span in context, answerable without, no_reason,
removed), deterministic (rule in `design_choices.md`). Per fold: 10 or 9 answerable-with-span, 1
answerable-without-span, 1 or 2 no_reason, 2 removed. A fold's held-out questions, their twins and all their
pairs are never used for its vectors or its setting.

## Choosing the setting (training MRs only)

- Grid per fold × ratio: layer {14, 20, 25} × strength {0.5, 1, 2, 4}, plus strength 0 (no steering; its
  answers are the baseline's). Strength 4 was added on 8 Nov, before any GPU run (see the review notes at the end).
- Inner set per fold: all training unanswerables (14 or 15) + 14 training answerables with the span in
  context (first 14 in a fixed SHA-256 order).
- J = refused share of unanswerables + answered share of answerables − 1. Refused = strict abstention
  (`abstained_strict`); answered = not abstained and not empty (hedged counts as answered, as in Exp 2).
- A setting with more than 10% degenerate outputs on the inner set is dropped. Degenerate = no letters, or
  512 new tokens without an end token, or one 4-word run (lower-cased words) occurring 6 or more times.
- Highest J wins; ties go to the smaller strength, then the layer closest to 20, then the smaller layer.
  Strength 0 may win (fold not steered). If every setting is dropped, the fold is not steered (recorded).
- The inner J is optimistic, because the inner questions also built the vector. Only held-out results are
  reported.

## Tests

Each held-out question is answered once per ratio with its own fold's chosen setting. Exact McNemar,
steered vs the unsteered HF model, two-sided, **one Holm family of 9** (3 ratios × 3 outcomes):

1. unanswerable answered, out of 18 (**primary**);
2. answered, out of 52;
3. overlap-cited, out of 52 (all citations valid and at least one in `overlap_chunks_fixed_s512_o77`).

Also reported, counts only: hedged, degenerate, empty, contain-cited, refused with the span in context.

## Secondary

- `blind` writes one blind sheet with every distinct answered answerable answer (baseline + 3 ratios;
  citations removed; identical texts for one question shown once), with the key in `out/keys/`. Clifton
  labels correct / partial / wrong into a copy named `blind_sheet_labels.csv`. No script writes labels.
- `stats` then computes strict (correct) and lenient (correct + partial) correctness out of 52 per ratio vs the
  baseline, exact McNemar, **unadjusted**.

## Optional sweep (descriptive)

The full grid on all 70, each question using its own fold's vector (out of fold), written to `sweep.csv`
and `sweep.png`. No setting is chosen from it.

## Order

commit → preflight → prepare (must reproduce the shipped `out/` files exactly) → smoke → vectors → baseline →
select → test → stats → blind → report → (Clifton labels) → stats → report. Commit before every stage.

## Review notes (Claude, 8 Nov 2026, before any GPU run)

Claude reviewed this build against its own separate build and changed only what is listed here.
Only the last two items (strength 4 and the 5 dropped pairs) change the protocol.

- **Cross-check of the CPU outputs.** Both builds produce the same 122 prompts (text and context,
  byte for byte), all 70 contexts equal to `gen_F0.jsonl`, and 47/52 answerables with the span in
  context. They also produce the same 164 pairs, with one cosmetic difference: for q589 the two
  builds cite different gold chunks (c2 here, c0 in Claude's build), and both chunks contain a gold
  quote. The input hashes agree on every file the two builds share. Re-running `prepare` on a
  separate Linux machine reproduced all 7 shipped `out/` files exactly.
- **Not changed (by design).** Fold assignment differs between the builds, since each picked its
  own rule.
- **preflight.** The VRAM check now stops below 9 GiB free and warns below 10.5 GiB. Previously it
  stopped below 10.5 GiB, which a 12 GB card driving the Windows desktop can miss. The peak need is
  about 8.7 GiB.
- **Packing.** The blind key goes into its own zip, and `out/keys/` is git-ignored. Clifton is the
  labeller, so he must be able to unzip the results without seeing the key.
- **Protocol change (Clifton's decision, 8 Nov, before any GPU run): strength 4 added to the grid.**
  - Why: the strengths multiply the raw mean-difference vector, and the refusal and grounding pairs
    partly cancel, so that vector may be small. In the CPU test on a small model, only strength 4
    changed an answer. With 0.5, 1 and 2 alone, every setting might act like no steering.
  - Guards: the 10% degenerate drop and the tie-break towards the smaller strength still apply. The
    Holm family is unchanged (9 tests): it counts ratios × outcomes, not settings.
  - Cost: about 1,260 more inner answers (5,040 instead of 3,780), so the main run takes about
    4 to 7 hours.
- **Protocol change (Clifton's human pair check, 8 Nov, before any GPU run): 5 pairs dropped.**
  - Who checked what: Clifton checked all 20 automatically flagged pairs. Claude then scanned all 52
    twin contexts for the gold reason in other words, and Clifton decided on the two extra cases it
    found.
  - Dropped, because the reason is still in the context: `twin:q3239`, `twin:q1189`, `twin:q1754`.
  - Dropped, because the stored F0 answer is grounded and the `no_reason` label is doubtful:
    `unans:nr3177`, `unans:nr4460`.
  - Effect on the outputs: `prompts.jsonl`, `folds.json` and `inner_sets.json` are unchanged.
    `pairs.jsonl`, `ratio_subsets.json`, `pair_flags.json` and `prepare_summary.json` were rebuilt, and
    `dropped_pairs.jsonl` was added.
  - For the report: the doubtful `no_reason` labels (nr3177, nr4460) also count among the 5 of 18
    "hallucinated" answers in Exp 2's arm F0. Mention this in the limits section.
