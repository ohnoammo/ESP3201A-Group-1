"""Run Clifton's score_baselines_labels.py unchanged, with two path overrides only (RUN_LOG D3, D4):
- LABELS: read the labels where they arrived (results/FOR_JAMES_baselines_labels/), not a copy;
- outputs: write to results/baselines_correctness_clifton_*.csv / _clifton.md, so that
  results/baselines_correctness.md (reserved for score_baselines_correctness.py) is not written.
Run from the repo root: python score_baselines_clifton_wrapper.py
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "results", "FOR_JAMES_baselines_labels"))
import score_baselines_labels as S

S.LABELS = os.path.join(S.RES, "FOR_JAMES_baselines_labels", "baselines_blind_sheet_labels.csv")
S.OUTS = {k: os.path.join(S.RES, f"baselines_correctness_clifton_{k}.csv") for k in ("per_arm", "tests", "rows")}
S.MD = os.path.join(S.RES, "baselines_correctness_clifton.md")
sys.argv = sys.argv[:1]          # never --force
S.main()
