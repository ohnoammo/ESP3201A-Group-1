# Run provenance (Exp 2 test arms, faithfulness, gate)

Recorded 23 Oct 2026 from the environment the runs used (same machine and session; nothing was
reinstalled or re-downloaded in between). Review items P10 and P11 (`reviews/methods_review_codex.md`).

## External Exp 1 code and inputs (P10)

`C:/Users/kwekt/ESP3201A_local/exp1_copy` is not a git repository, so files are identified by
SHA-256. Code files were last modified 22 Oct 14:47 (+0800), before test generation (4a8782f,
22 Oct 22:42); `relations.py` and `chunking.py` are byte-identical to `ESP3201A_SWE_exp1_2210`
(also not a git repository).

| file | SHA-256 |
|---|---|
| exp1_copy/relations.py (expand_and_pack, token_counter) | f0d493c193f42a98fe82c9c08a7b396a1027d67397833da14c888c1b55236e22 |
| exp1_copy/chunking.py | e2e50c476141a3ed36477cf89f0812439206fc1193b3ad5ab4823b99252b13a4 |
| exp1_copy/pr_document.py | 5ba6533aff77d1407836f9d6959150abb0ff7facd555f93cd859eb0d0ae67941 |
| exp1_copy/retrieve.py | 3ef9d0fd830a16156ddc00d9a50e220f230ccd379deadc3f7631143e0f65da54 |
| exp1_copy/dense_retrieval.py | 0a7c8f9647719a3c360d4d233701bc87bf2cced35ceb5b1e3771558e2ab0e26d |
| exp1_copy/exp1_common.py | 700c9b395afbf9ceb335a2b229a425cb0fb605ff1201fa1eabefa294e00aaf0b |
| exp1_copy/chunks/swe_fixed_s512_o77_2231docs_311d0480.json (pool A fixed) | 1030bdba497864fb31e0fcd648f0203440c290c3e4f37c58d96a17b017e04c1a |
| exp1_copy/chunks/swe_struct_c256_2231docs_0611be80.json (pool A structural) | f780b7b8ffe8df9fc9a675e6b62dab79673586fd1511c8a57487dab6eada0774 |
| exp1_copy_redacted/chunks/swe_fixed_s512_o77_2231docs_311d0480.json | 4719ddf71d5c04e0d993fb5133f9cfe642bc6df8e02dc5d7fe20baaede623493 |
| exp1_copy_redacted/chunks/swe_struct_c256_2231docs_0611be80.json | 7bb3b3eb7a35f1866c4bec8f9add0371fdf9dfae6c55b983209c55417e308979 |
| links_fixed_s512_o77.json (Exp 2 links, `link_map.py`) | 95843582c072a77c0ddc7e56e47a513042b2e6e0ed08d87f69f3f254e8dc448b |
| links_struct_c256.json | 5424e583b0620ab87079d31b250dc95ddcb2ae95a859df45b59c025e5651be57 |
| exp1_copy/prs (2,278 PR JSON files; SHA-256 of the sorted `sha256sum` listing) | c539bd5fcedca674540d22fc2850f4609acf8afea9a04d9115d0a10f54847b75 |
| exp1_copy_redacted/prs (2,278 files, same method) | a54869db16c7cf5eec7a8d66d4c69d3fff8f46ecb4a1517e243f0409ca6dd16b |

## Faithfulness judges (P11)

Loaded by name without `revision` (`faithfulness.py`); the Hugging Face cache holds:

| model | revision | note |
|---|---|---|
| lytang/MiniCheck-Flan-T5-Large | main = 96eafd01cee2d16cf81aaa2fb226b14f422a37b3 (config, tokenizer, pytorch_model.bin) | the cache also holds refs/pr/2 = c3f6482d13e7cc81748e853723befc286f29d949 (model.safetensors only). See "MiniCheck weights check" below: the weights are identical either way. |
| vectara/hallucination_evaluation_model (HHEM-2.1-Open) | de9a5e6ba9ba49531a022dba17e35ffeb2a6fad8 | trust_remote_code module cached under the same hash |
| google/flan-t5-base (HHEM's tokenizer/backbone config) | 7bcac572ce56db69c1ea7c8af255c5d7c9672fc2 | |

### MiniCheck weights check (23 Oct)

- refs/pr/2 is Hugging Face discussion #2, "Adding `safetensors` variant of this model", an open
  automated pull request by SFconvertbot against refs/heads/main (created 2024-12-20): the
  safetensors conversion of main's `pytorch_model.bin`.
- Per-tensor SHA-256 (dtype + shape + raw bytes), on CPU, offline:
  - main `pytorch_model.bin`: 560 tensors; pr/2 `model.safetensors`: 558. The 2 extra in the .bin
    are `encoder.embed_tokens.weight` and `decoder.embed_tokens.weight` (tied copies of
    `shared.weight`, which safetensors stores once). All 558 common tensors are identical.
  - State dict loaded by `AutoModelForSeq2SeqLM.from_pretrained("lytang/MiniCheck-Flan-T5-Large")`
    (as in `faithfulness.py`): 560 tensors, 560/560 identical to main's .bin and 558/558 to pr/2.
  - Aggregate SHA-256 of the loaded state dict (sorted `name:tensor-hash`):
    5d86435c72e2dee611125eafacf2cc4563df5137689a2dde76cbb6b23b943311.
- So the scores used main's weights, whichever file supplied them. Pinning `revision=96eafd0...`
  reproduces them.

## Libraries and runtime

| item | version |
|---|---|
| Python | 3.11.0 |
| transformers | 5.14.1 |
| torch | 2.14.0+cu130 (CUDA 13.0) |
| tokenizers | 0.22.2 |
| huggingface_hub | 1.30.0 |
| numpy / scipy | 2.4.6 / 1.17.1 (stats, AUROC, Spearman, Wilcoxon) |
| sentence splitting | Python standard-library `re` (`faithfulness.sentences`), no NLP library |
| GPU | NVIDIA GeForce RTX 5070, driver 616.56 |
| Ollama (generation) | 0.40.4; model digests qwen3:4b-instruct-2507-q4_K_M 0edcdef34593, qwen3:8b 500a1f067a9f (recorded per row) |

## Project commits

Generation 4a8782f (results committed 8d00a33); faithfulness answerables 65d3d7f (659 rows),
unanswerables b5abc75 (141 rows); every faithfulness row records its commit.

## Correctness inputs (1 Nov)

Both label files are committed as inputs (1 Nov); SHA-256 of the committed versions:

| file | SHA-256 | origin |
|---|---|---|
| `judging/codex_labels.csv` | 806d14ecc7231c4b3c27a2de998d1a5e613731d840414f15259ed2d771ed238c | Codex blind labels, 659 rows (23 Oct) |
| `judgements/validation_sample_alyssa.csv` | e7cea708b512b9f34d7cb1aeb2c0ad2fcd42edabca344d58f2dc5feb8fdf775a | Alyssa, 80 rows; duplicate J0318 replaced with her original J0322 label by the owner, 1 Nov 15:14 |
| `judging/validation_sample.csv` | d608626b5d380faaae455285e9c631dbc63edc7660bfef3406e88167af100171 | blind sample Alyssa labelled from (build_judging.py, 23 Oct) |
| `judging/keys/judging_key.json` | 4deadcd76f58e095420d5c3a706159bfaa140a0f027f5b025aaace199bdc2386 | blind_id -> row key (build_judging.py + extend_judging.py, 23 Oct) |

Alyssa's file matches `validation_sample.csv` on all 80 blind ids (same order) and on question, gold
answer, gold quotes and model answer, except 7 carriage returns (`\r`) missing from the gold quotes of
J0029, J0162 and J0513 (spreadsheet save); `agreement.py` compares text with line endings normalised.

## Failure-analysis input (1 Nov)

`judgements/gate_pass_sample_alyssa.md` (Alyssa's tags on the 10-row gate-pass sample from `gate_pass_sample.py`, 31 Oct), committed 1 Nov, SHA-256 efa4ccd0066e2bd2087d46e965039d4c22a444bafe4c30085dd68fb924a27a3a. `judgements/gate_pass_tags_clifton.md` is not used.

## Arm W-F Codex labels (1 Nov)

| file | SHA-256 | origin |
|---|---|---|
| `judging/codex_labels_w.csv` | 8097fcfc312f5b41f370fc96eae3d8d00cec9dacfb8bad61207a23476743f878 | Codex, 153 rows: W-F J0660-J0792 (133) + 20 re-judged old ids (drift check only, never used in analysis) |
| `judging/codex_labels.csv` | f47f947285e2ee8aa809f03dfcac8943bcaa3296271d8528fac3c4f35d840c46 | 23 Oct file (806d14...ed238c) byte-identical + the 133 W-F rows appended by `merge_w_labels.py` |

Drift check: `results/codex_drift_check.json` (17/20 agree, kappa 0.758; the 3 changes are partial -> correct).

## Arm H0 (5 Nov)

Rule `tuning_rule_hybrid.md` (63f62a9, amendment 18db7de), before any hybrid run. Generation at 84e316c (rows committed f5dbc03); scoring at de77536; faithfulness at c2e811c (177 + 33 rows).

| item | value |
|---|---|
| BM25 tokenizer library | nltk 3.10.3 (Exp 1's pin), installed in `C:/Users/kwekt/ESP3201A_local/pylib_h0`; hybrid candidates byte-identical to a 3.10.4 build |
| Index copy | `C:/Users/kwekt/ESP3201A_local/exp1_copy_hybrid`, `qdrant_exp1/meta.json` SHA-256 bb6fb7722d7f26d4a88d0dceb8c7105814553a5b926693b04384e5e4d09700b3 |
| Redacted index copy | `C:/Users/kwekt/ESP3201A_local/exp1_copy_redacted_hybrid`, `qdrant_exp1/meta.json` SHA-256 bf84caefe67a656959e5c8c2fbf605d3ec4b8657edb7961cd81cf72a82c87ec3 |
| Frozen indexes | `exp1_copy` 6d599f58...1eeed513 and `exp1_copy_redacted` fd8dc25d...ba61e45e, rechecked 5 Nov after all H0 runs: unchanged |
| Codex model | not recorded for the H0 session |

| file | SHA-256 | origin |
|---|---|---|
| `judging/codex_labels_h.csv` | ae71cc4bfe0f012e78b9d15dacb952d9d5d7e4172c6335d4bf7ff77cd3ed5741 | Codex, 197 rows: H0 J0793-J0969 (177) + 20 re-judged old ids (drift check only, never used in analysis) |
| `judging/codex_labels.csv` | 12d2d522dbee20a9f7d442942c1d352b71d4c0df31acf2fe0b203f8482d892e8 | 1 Nov file (f47f94...840c46) byte-identical + the 177 H0 rows appended by `merge_h_labels.py` |
| `judging/codex_pack.csv` | ee82af58810b7ba442ef3314a26b0c84249bda3b21a00b551fc6f385cc4b422d | 792-row pack byte-identical + 177 H0 rows (`extend_judging.py`) |
| `judging/keys/judging_key.json` | 0294dc07f8d7c34a589e4b0d0ce2c95db9f32603d81a4fe9a3a9c2e207a495eb | updated by `extend_judging.py`; read only by scripts |

Drift check: `results/codex_drift_check_h.json` (18/20 agree, kappa 0.783; J0218 partial -> correct, J0345 correct -> partial). Frozen `stats_correctness.csv` reproduces with the merged labels (values identical; label-hash and commit columns not recommitted), as does `gate_eval.csv` for F0 (`gate_h0.py`) and `summary_faithfulness.csv`.

## SymPy transfer check (imported 5 Nov)

`ESP3201A_SWE_exp1_sympy.zip` SHA-256 2af013a7e49e6a34c70eb4be87a7ba38e711fb8c65f3b8867580b82545d37937; per-file hashes in `results/sympy/MANIFEST.json`. Exp 2 rows: qwen3:4b-instruct-2507-q4_K_M, digest 0edcdef34593, Ollama 0.40.4, prompt v3 with 'Django' -> 'SymPy' (sha1 63fe408275, based on 759a5e1219), RTX 3050 Ti Laptop, Clifton's machine. Django Exp 1 comparison: `ESP3201A_SWE_exp1_2510/ESP3201A_SWE_exp1/results/stats_test_poolA_full.txt` SHA-256 0ce3524978757daa458b0e1d1abb69d7a441d68adafef3f50a02e986e3185312. No code from the zip was run here.
