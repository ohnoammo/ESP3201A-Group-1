# Relation-factor tuning rule for Exp 2 (written and committed BEFORE running; James, 22 Oct)

Data: dev set 2 only (`questions_dev2.jsonl`, 40 answerable; no-reason rows not used here).
Retrieval only (no LLM). Pool A (new, same-ticket filter). Budget 2,560 tokens (Exp 1 unit).
Packing: Exp 1 `relations.expand_and_pack` with Exp 2 links (`pack_exp1.py`), score 1/rank.

Per chunking (fixed_s512_o77, struct_c256) separately:
1. Grid alpha in {0, 0.25, 0.5, 1}.
2. Metric: "any span" rate = share of answerable questions where at least one quote span is fully
   covered by the union of chunks in the packed context.
3. Safety rule (group option B): reject any alpha whose answer-PR-in-budget rate is more than
   0.02 below the rate at alpha 0.
4. Pick the eligible alpha with the highest "any span" rate. Ties go to the smaller alpha.

Implemented in `select_alpha_dev2.py`; its output is saved to `results/alpha_selection_dev2.json`.
