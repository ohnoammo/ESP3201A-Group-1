# Codex prompt for arm H0 labels (tuning_rule_hybrid.md)

Run in the `ESP3201A_Exp2` folder with branch `hybrid-h0` checked out (the rows below are not on `master`).
Use the same Codex model as the 23 Oct and 1 Nov sessions if possible, and record which model ran.

```
You are judging model answers for a research experiment. Work only in this folder.

Read judging/codex_instructions.md and follow it exactly. The rows to judge are in
judging/codex_pack.csv.

Judge these 197 rows:
- J0793 to J0969 (177 rows)
- J0145, J0218, J0225, J0235, J0253, J0258, J0260, J0267, J0328, J0330, J0345, J0374, J0402,
  J0411, J0476, J0535, J0570, J0609, J0634, J0641 (20 rows)
Judge every row on its own, against its gold quotes, with the same standard for all rows.

Write the results to a NEW file judging/codex_labels_h.csv with exactly the columns
blind_id,label,note (one row per id, 197 rows, label = correct / partial / wrong, note = one
line). Do not create or change any other file.

Do not open, read or search judging/codex_labels.csv, judging/codex_labels_w.csv, judging/keys/,
judging/validation_sample.csv, judgements/, results/ or any other file, and do not run git.
You need only codex_instructions.md and codex_pack.csv.

When done, report: the number of rows written, the count per label, and any id you could not judge.
```
