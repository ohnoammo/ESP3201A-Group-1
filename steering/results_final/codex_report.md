# Activation steering on the 70 GitLab Runner questions (Codex build): results

**What this is.** Activation steering (contrastive activation addition) on the frozen Qwen3-4B-Instruct-2507 (Hugging Face, bf16, greedy). No weights were changed. This is **not reinforcement learning and not fine-tuning**. The professors asked for reinforcement learning of weights on the human-checked set; this experiment instead uses the checked set to build a steering vector, and the report must say so.

Model revision `cdbee75f17c01a7cc42f958dc650907174af0554`, torch 2.14.0+cu130, transformers 5.14.1, GPU NVIDIA GeForce RTX 5070, code sha `95974b01ac79`, repo HEAD `657eda1`.

**Provenance of the 70.** The question check was mostly automated (DeepSeek and Codex); James read about 11 rows himself. The Exp 2 correctness labels are provisional (James 20, Codex 67, Alyssa none, kappa 0.177). The gold answers, used here as the chosen side of the grounding and twin pairs, were written by Claude.

## Setup checks

- Rebuilt main contexts equal `gen_F0.jsonl`: True (70/70).
- Answerable questions with the answer span in context: 47 of 52 (all quotes inside: 46).
- Pairs: {"grounding/g_nf/not_found_sentence": 47, "grounding/g_what/what_as_why_title": 47, "refusal/twin/gold_answer_top_twin_chunk": 49, "refusal/unans/stored_F0_answer": 3, "refusal/unans/what_as_why_title": 13}.
- Smoke test: {"response mask matches the chat template ['Not found in']": true, "response mask matches the chat template ['Because of a']": true, "greedy output identical twice [main:q1383]": true, "greedy output identical twice [main:rm3265]": true, "hook changes the output": true, "no hook left on any layer after steering": true, "removing the hook restores the unsteered output [main:q1383]": true, "removing the hook restores the unsteered output [main:rm3265]": true, "a zero vector through the hook gives the unsteered output": true, "prefill: position before the last is untouched": true, "prefill: last prompt position is changed": true}.
- Pipeline check, HF unsteered vs stored Ollama F0 (answer vs refuse): 63/70 agree, kappa 0.746; table {"ollama_answered/hf_answered": 48, "ollama_not/hf_answered": 7, "ollama_not/hf_not": 15}. Not a baseline.

## Vectors

| Layer | Typical residual norm | Vector norm / typical (range over 15 fold x ratio) | Min cosine between folds |
|---|---|---|---|
| 14 | 40.1 | 0.082 to 0.199 | 0.993 |
| 20 | 59.7 | 0.108 to 0.238 | 0.993 |
| 25 | 127.7 | 0.138 to 0.271 | 0.995 |

## Chosen settings (inner J, training MRs only; optimistic and not a result)

| Ratio | Fold 0 | Fold 1 | Fold 2 | Fold 3 | Fold 4 |
|---|---|---|---|---|---|
| 40:60 | unsteered (J +0.67) | unsteered (J +0.53) | unsteered (J +0.57) | unsteered (J +0.71) | unsteered (J +0.57) |
| 50:50 | unsteered (J +0.67) | unsteered (J +0.53) | unsteered (J +0.57) | L20 x4 (J +0.79) | unsteered (J +0.57) |
| 60:40 | L20 x2 (J +0.73) | L20 x4 (J +0.66) | L20 x4 (J +0.64) | unsteered (J +0.71) | L20 x2 (J +0.64) |

## Held-out counts

| arm | unans_answered_of_18 | answered_of_52 | overlap_cited_of_52 | contain_cited_of_52 | refused_with_span_in_context | hedged_of_70 | degenerate_of_70 | empty_of_70 | n_steered_questions |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 7 | 48 | 45 | 45 | 0 | 0 | 0 | 0 | 0 |
| steered 40:60 | 7 | 48 | 45 | 45 | 0 | 0 | 0 | 0 | 0 |
| steered 50:50 | 5 | 44 | 37 | 37 | 1 | 0 | 0 | 4 | 14 |
| steered 60:40 | 6 | 43 | 17 | 17 | 4 | 0 | 1 | 1 | 56 |

## Tests: exact McNemar vs the unsteered HF model, two-sided, one Holm family of 9

| Ratio | Outcome | n | Unsteered | Steered | Only unsteered / only steered | p | Holm p |
|---|---|---|---|---|---|---|---|
| 40:60 | unanswerable answered (primary) | 18 | 7 | 7 | 0 / 0 | 1.0000 | 1.0000 |
| 40:60 | answered | 52 | 48 | 48 | 0 / 0 | 1.0000 | 1.0000 |
| 40:60 | overlap-cited | 52 | 45 | 45 | 0 / 0 | 1.0000 | 1.0000 |
| 50:50 | unanswerable answered (primary) | 18 | 7 | 5 | 2 / 0 | 0.5000 | 1.0000 |
| 50:50 | answered | 52 | 48 | 44 | 4 / 0 | 0.1250 | 0.7500 |
| 50:50 | overlap-cited | 52 | 45 | 37 | 8 / 0 | 0.0078 | 0.0625 |
| 60:40 | unanswerable answered (primary) | 18 | 7 | 6 | 1 / 0 | 1.0000 | 1.0000 |
| 60:40 | answered | 52 | 48 | 43 | 5 / 0 | 0.0625 | 0.4375 |
| 60:40 | overlap-cited | 52 | 45 | 17 | 28 / 0 | 0.0000 | 0.0000 |

## Correctness (secondary, labels `blind_sheet_labels.csv`, exact McNemar, unadjusted)

| Kind | Ratio | n | Unsteered | Steered | Only unsteered / only steered | p |
|---|---|---|---|---|---|---|
| strict (correct) | 40:60 | 52 | 39 | 39 | 0 / 0 | 1.0000 |
| strict (correct) | 50:50 | 52 | 39 | 31 | 8 / 0 | 0.0078 |
| strict (correct) | 60:40 | 52 | 39 | 12 | 27 / 0 | 0.0000 |
| lenient (correct + partial) | 40:60 | 52 | 47 | 47 | 0 / 0 | 1.0000 |
| lenient (correct + partial) | 50:50 | 52 | 47 | 38 | 9 / 0 | 0.0039 |
| lenient (correct + partial) | 60:40 | 52 | 47 | 20 | 27 / 0 | 0.0000 |

## Optional sweep (descriptive only; no setting was chosen from it)

See `sweep.csv` and `sweep.png`.

## Limits

- With 18 unanswerable questions, Holm over 9 tests needs a lopsided split (about 7 to 0 before correction) to reach significance. A non-significant result does not show steering has no effect.
- The inner J is optimistic: the inner unanswerables also built that fold's vector.
- Twin and grounding pairs use Claude's gold answers; WHAT-as-WHY rejections are scripted from MR titles; only the 5 stored Ollama answers to unanswerables are real model errors.
- The F0 contexts and pairs come from the q4_K_M Ollama run; the steered model is the bf16 HF model.
- Correctness labels (if present) come from one rater.
