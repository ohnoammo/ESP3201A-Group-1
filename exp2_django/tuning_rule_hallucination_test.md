# Stronger hallucination test, H0 vs F0: rule file (DRAFT, 5 Nov, not committed, nothing run)

To be committed before any new question is built or generated, once the open items below are decided.

**Question.** Does hybrid retrieval change how often the model answers questions whose reason is not in the PRs,
compared with dense?

**Status.** Proposed after the Django and SymPy H0 counts were seen, so those results shaped the design. It uses
**new questions only**, and none of its rows have been generated. It is its own one-test family. It changes no frozen
arm, label or finding, and the 17 existing unanswerables are not part of it.

## Primary test (one test only)
- **Model and prompt:** 8B, prompt v3. The 8B answers 13 of 17 existing unanswerables under F0, so it has room to fall;
  the 4B on v3 answers 3.
- **Outcome:** answered, strict abstention rule (`score.py`), hedged = answered.
- **Test:** H0 vs F0, paired by question, exact two-sided McNemar, alpha 0.05. No Holm, because it is the only test.
- **What it takes:** 6/0 (p = 0.031), 8/1 (p = 0.039) or 9/2 (p = 0.065, not enough).
- **Reported:** b, c, exact p, and the Newcombe 95% limits from `limit_hybrid.py`.

## Arms
F0 and H0 exactly as in `tuning_rule_hybrid.md`: fixed 512/77, alpha 0, budget 2,560, score order, Ollama 0.40.4,
temperature 0, seed 42, num_ctx 8192, num_predict 512, think off, frozen prompt and model digest. Both arms run on the
RTX 5070, because 9 of 22 SymPy answers changed across GPUs with identical contexts.

## New questions
Two types, built before any generation, in a fixed SHA-256 order, with no hand-picking and no stopping based on results.

1. **Redacted reason.** Source: the 50 answerable test questions, minus the 5 whose PRs already have an unanswerable
   variant (9789, 11459, 12342, 13671, 16129), so at most 45. Same question; the answer span and its repeats are removed
   from the PR before chunking (`leakage_variant.py` method; diffs are never edited); same-ticket PRs excluded.
2. **Real no-reason.** Source: pool A PRs not used anywhere in Exp 2 and not sharing a ticket with one. A question is
   written from the change, then a human confirms that no reason is stated anywhere in the PR.

Not used: whole PR removed. The 4B abstained on all 5 in F0 and H0, so more would add few changes.

**Check for every question, by a human who has not seen any answer:** read the redacted or no-reason PR and record keep
or drop, with the reason. Drop if the reason can still be read or inferred from the text or diff. This is the same
standard that dropped rk11459. **Expect losses:** 3 of the 5 earlier redactions were dropped, and at that rate about 18
of the 45 would survive, so type 2 is needed to reach the target.

**Target:** 50 kept questions. **Minimum:** if fewer than 30 are kept, no test is run and only counts are reported.

## Index
New redacted copies outside OneDrive, for dense and BM25, in the way `exp1_copy_redacted_hybrid` was built. Frozen indexes
stay read-only and their hashes are rechecked. Regression before generation: F0 contexts for the existing questions
are unchanged in the main copies.

## Supporting measures (no tests)
- **Claim-level labels:** two blind human raters split each answered row into claims and tag each as supported, invented
  reason, borrowed from another PR, or what-as-why (the `results/failure_analysis.md` categories). Arm hidden, citations
  removed. Reported as counts per arm with agreement. Unit of inference stays the question.
- **Faithfulness and gate:** MiniCheck and HHEM counts as in `tuning_rule_hybrid.md`. They do not decide the outcome,
  because their discrimination is weak (AUROC about 0.55 and 0.70).
- **4B v3:** the same counts, no test.
- **Error against answers given (existing data, already seen):** on the 50 Django answerables, wrong and partial among
  answered, per cell. Labelled as post hoc.

## Wording
- "Hybrid reduces hallucination" only if the test has p < 0.05 with fewer answers under H0 **and** answered /50 and answer
  span in context did not fall in the existing 8B v3 cell (they did not: 40 -> 45 and 42 -> 43). "Increases" likewise.
- Otherwise: "no evidence of a change on N new questions", with the limits. Never "no effect" or "equivalent".
- 50 questions can only detect fairly large effects: 6/0 is a net fall of 12 points on 50 questions.
- Results apply to Django only, and to questions built this way.

## Open before committing
1. Target and minimum (50 and 30 above).
2. Who checks the questions and who labels claims. They should be people, and not the same person for both if possible.
3. Whether it fits the report deadline: roughly question building and checking, a new index, 100 8B rows, then labelling.
