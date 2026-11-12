# Arm H0 on SymPy, 4B v3: rule file (5 Nov)

Committed before any hybrid retrieval or generation on the SymPy questions, but after the Django H0 results and
Clifton's SymPy F0 results were seen. **Exploratory, counts only, no tests, no Holm family.** It changes no frozen
arm, label or finding.

**Question.** Does the Django H0 pattern repeat on SymPy: more answers, more correct, and little change in
unanswerable answers?

## Arm
H0 = Clifton's SymPy F0 with one change: hybrid ranking (RRF of code-aware BM25 k1 1.2, b 0.75 + dense, k = 60,
depth 100), as in `tuning_rule_hybrid.md`. Same pool, chunk set 394f364b, alpha 0, budget 2,560, score order, the same
22 questions, 4B, prompt v3 for SymPy, Ollama 0.40.4, temperature 0, seed 42, num_ctx 8192, num_predict 512, think off.

BM25 query = the question text. Dense query = the question with the SymPy "why" instruction.

## Hardware control
Clifton's F0 ran on an RTX 3050 Ti, and this runs on the RTX 5070. So F0 is rerun here as well (22 rows).
- Stop if the rebuilt F0 contexts differ from Clifton's on any question.
- Report how many rerun answers are identical to his, and F0 counts from both runs.
- The comparison for H0 is against the F0 rerun on the same GPU, with Clifton's F0 shown alongside.

## Scoring
`exp2_sympy.py` score rules (a copy of `score.py`). Reported: span in context /15, gold PR in the first 5 ranked PRs /15,
answered /15, overlap-cited /15, unanswerable answered /7, with question ids.

## Correctness labels
- One blind sheet, shuffled by SHA-256, arm hidden, citations removed: H0 answered answerables, Clifton's F0 answered
  answerables, and any F0 rerun answer whose text differs from his.
- Same `LABELLING.txt` rules and same two raters if available. Merge rule as in
  `results/sympy/LABEL_MERGE_RULE.txt`: lower label, upper as sensitivity.
- Re-labelled F0 rows are a drift check and never replace Clifton's F0 labels.

## Wording
Counts only. With 7 unanswerables and 15 answerables, no result may be written as "hybrid reduces" or "hybrid does not
reduce" hallucination on SymPy. Allowed: "the pattern did or did not repeat", with the counts.

## Amendment (5 Nov, before any hybrid retrieval result was used or any generation)
Dense rankings on this machine differ slightly from Clifton's saved candidates: query embeddings shift by about 0.0001 between machines, top-100 overlap is 99-100, and the first rank difference is 5 at the earliest. So the dense half of H0 is not bit-identical to his F0 ranking. This is recorded per question in the candidates file and is not a stop condition. The stop condition stays as written: F0 contexts rebuilt from his saved candidates must equal his rows.
