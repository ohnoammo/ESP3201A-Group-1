# Overnight summary (11-12 Nov 2026)

**Finished:** all tasks except Task 3.2 (GitLab H0 vs F0), which was skipped because no GitLab `gen_H0.jsonl` exists. The work is on branch `exp2-baselines` of the **OneDrive** `gitlab_runner_copy`, last commit before the zip `ef00e48`. Read `results/exp2_baselines_report.md`; every step is in `results/RUN_LOG.md`.

**Headline numbers** (4B, 70 questions; lenient refusal scoring, pre-registered):
- **Unanswerables answered /18:** F0 5, P0 (plain RAG) 13, CB (closed book) 18.
  - F0 vs P0: 0/8, Holm p 0.023. F0 vs CB: 0/13, Holm p 0.001.
- **Answerables answered /52:** F0 43, P0 47 (n.s.), CB 51 (Holm p 0.043). Answered is not correct.
- **Caveat on F0 vs P0:** it is less sturdy than the p value suggests.
  - P0 `nr3147` is a refusal in bold that the regex misses. Counted as a refusal, it gives Holm 0.047, and 0.094 under the broad regex.
  - Four P0 rows reject the question's premise. If all five are non-answers, the result is 0/3, p 0.25.
  - F0 vs CB holds under any reading.
- **Gate (exploratory), F0:** unanswerables 5 → 2, answerables 43 → 42, provisionally correct 33 → 32. It matches the 6 Nov gate exactly (48/48 decisions).
- **Gate, P0:** 13 → 0 and 47 → 4. The gate removes uncited answers by rule, so this mostly shows P0 rarely cites.
- **Retrieval carry-through (F0):**
  - Evidence in context (47): 42 answered, 33 correct.
  - Evidence not in context (5): 4 refused, 1 answered wrongly.
- **Reproducibility:** the F0 re-run gave 9/10 identical answers on the first check, and 70/70 on the full re-run. Ollama stayed at 0.40.4 with the same model digest.

**Decisions taken without you** (all logged with reasons):
1. Worked in the OneDrive copy, not `ESP3201A_local`, because `..\ESP3201A_Exp2` only resolves from there. The data was checked identical between the two. I used a new branch, because the local copy's `gitlab-runner-pilot` has 5 codex-steering commits this copy lacks.
2. P0's user message is `{context}\n\nQuestion: {question}`, mirroring F0's template.
3. The full F0 re-run ran whatever the 10-question result was. It is a sensitivity only.
4. F0's provisional labels were mapped by recomputing `score`'s blind-id order and checking every row's text. `keys/` was not opened.
5. Blank sheet: strict-answered answers (a superset of lenient), one row per distinct answer. It has 147 rows.
6. After advisor check 1 and before any generation, I added a pre-registered **broad-refusal sensitivity regex**. The primary regex is unchanged.
7. Jobs write their own logs and progress bars (no `Tee-Object`, which breaks `\r` bars in PowerShell 5.1). Job windows now have QuickEdit turned off.
8. The F0 re-run **froze for an hour**: its window was left in QuickEdit "Select" mode, and it had written 0 rows. I killed it and relaunched it, and it then finished fine.
9. Figure: grouped bars on one percentage axis. Only `steering_tradeoff.svg` exists (no `.png`), so I matched its colours.
10. The zip was built after this summary so that it includes it.

**Advisor findings:**
- **Check 1:** the regex misses free-form refusals. Fixed with the broad sensitivity, plus 5 minor fixes, all before generation.
- **Check 2:** an independent recount of every count, b/c and p: **MATCH**.
- **Check 3:** the `nr3147` and premise-rejection issue above, and an overclaiming figure. Both are fixed, with no scores changed.

**For you this morning:**
1. **Read P0's 13 and CB's 18 answered unanswerables** in full (`gen_P0.jsonl`, `gen_CB.jsonl`; ids in `results/baselines_unanswerable_answered.csv`). Decide how premise rejections count before claiming "grounding beats plain RAG".
2. **Get `results/baselines_blind_sheet_blank.xlsx` labelled** with `exp2_gitlab_A2000/LABELLING.txt`. Don't open `results/keys/`.
3. **Alyssa's review** of the 87 F0/C1 rows is still due. All correctness numbers stay provisional until then.
4. **Send `results/exp2_baselines_bundle.zip` to Clifton.** I didn't send it.
5. **Housekeeping:**
   - Resume OneDrive sync, and close the 5 job windows.
   - `HANDOVER.md` is not updated, since I only created new files.
   - Merge `exp2-baselines` where you want it.
