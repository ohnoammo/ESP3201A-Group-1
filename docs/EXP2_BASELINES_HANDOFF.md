# Handoff: Exp 2 baselines, correctness, tagging, app (state as of Thu 12 Nov 2026, 18:10 SGT)

Read `claude/AI_HANDOFF.md` (Exp 1 + early Exp 2), `claude/STEERING_HANDOFF.md` and `claude/STEERING_RESULTS.md` first. This file covers the work from 11–12 Nov. The report is due **Fri 13 Nov 2026, 12:00 SGT**.

## People and plan
- **James** is running everything and writing the first draft of the report. **Clifton** is sick, but he labelled the 147-answer correctness sheet. **Alyssa** is out of the picture for now.
- **Plan:** James gets the draft to Clifton and Alyssa by about 22:00 Thu; they check it Fri morning; submit before 12:00.
- **Claude's role:** advisor. Claude Code runs things on James's laptop. This chat can list James's folders but cannot read file contents or run commands.

## Where things are
- **Root:** `C:\Users\kwekt\OneDrive - National University of Singapore\Documents\NUS Year 2\Claude code\ESP3201A\`
- **Baselines work:** `gitlab_runner_copy\`, branch **`exp2-baselines`** (not merged, not pushed).
  - Commits, in order:

    | Commit | What |
    |---|---|
    | `1b9aee9` | Overnight run, final |
    | `e56c1f9` | Clifton's labels, committed before unblinding |
    | `4273d42` | Labels re-stored byte-exact (`.gitattributes` fix) |
    | `9b71aeb` | Correctness results |
    | `9727751` | Log entry |
    | `c52e13e` | Tag agreement + tag files |

  - **Not committed:** James's edited `results/baselines_unanswerable_full.xlsx`, `ADVISOR_NOTES.md` and `codex_steering/`.
- **Rule file:** `tuning_rule_baselines.md`, committed before any generation.
- **Generations** (in `exp2_gitlab_A2000\`):

  | File | Contents |
  |---|---|
  | `gen_P0.jsonl` | Plain RAG |
  | `gen_CB.jsonl` | Closed book |
  | `gen_F0_rerun.jsonl` | F0 re-run, 70/70 byte-identical to `gen_F0.jsonl` |
  | `gen_F0_repro10.jsonl` | 10-question reproducibility check, 9/10 identical |
  | `run_meta_baselines.json` | Run metadata |

- **Results** (in `results\`):

  | File | Contents |
  |---|---|
  | `OVERNIGHT_SUMMARY.md` | Summary of the overnight run |
  | `exp2_baselines_report.md` | Main report: Tasks 1–3 + "Correctness (secondary)" section |
  | `RUN_LOG.md` | Every decision taken without James |
  | `baselines_counts.csv`, `baselines_tests.csv`, `baselines_rows.csv` | Task 1 counts, tests, per-row data |
  | `baselines_audit_lenient.csv`, `baselines_audit_broad.csv` | Audit lists for the lenient regex |
  | `baselines_gate*.csv/json/jsonl` | Task 2 gate |
  | `baselines_carry*.csv`, `baselines_django_extract.csv` | Task 3 carry-through |
  | `baselines_correctness.csv/.md` | Correctness; plus `baselines_correctness_clifton_*` from Clifton's script via a wrapper; they agree |
  | `baselines_unanswerable_answered.csv` (first 200 chars), `baselines_unanswerable_full.xlsx` (full answers, 41 rows incl. F0/F0_rerun) | Answered unanswerables for tagging |
  | `unanswerable_tags_agreement.md` | James vs Codex tagging, plus a post hoc section |
  | `baselines_tradeoff.png` | Figure: grouped bars of answered /18 and /52 for CB, P0, F0, F0+gate |
  | `exp2_baselines_bundle.zip` | Bundle for Clifton (built overnight, before correctness and tagging) |
  | `FOR_JAMES_baselines_labels\` | Clifton's labels (`baselines_blind_sheet_labels.csv/xlsx`), README, `score_baselines_labels.py` |
  | `keys\` | Blind key; opened only after Clifton's labels were final |

- **Two copies exist.** Claude Code worked in the **OneDrive** `gitlab_runner_copy`, not `ESP3201A_local`, so the two have diverged. **Not yet decided which is master.**
- **App:** `ESP3201A_SWE_exp1_app\` (its own git repo, created 12 Nov).

## Design (pre-registered in `tuning_rule_baselines.md`)
- **Arms** (all on the 70 GitLab Runner questions: 52 answerable, 8 no_reason, 10 removed; Ollama `qwen3:4b-instruct-2507` q4, settings copied from F0):

  | Arm | Prompt | Context |
  |---|---|---|
  | F0 | Strict grounded: cite or say "Not found in the provided PRs" | Dense, fixed 512/77, alpha 0, 2,560 tokens |
  | P0 | Plain RAG: "You are a helpful assistant. Use the following context…" | Same context ids as F0 |
  | CB | Closed book | None |

- **Primary scoring:** lenient refusal regex, applied to all arms. Secondary: strict `abstained_strict`.
- **Tests:** exact McNemar, F0 vs P0 and F0 vs CB, on unanswerables answered /18 and answerables answered /52, in one Holm family of 4. Sensitivity analysis without nr3177/nr4460.
- **Gate:** MiniCheck cited-min < 0.5 → abstain; threshold unchanged from Django. An answer with no valid citation is gated (pre-registered).

## Results

### 1. Pre-registered (lenient scoring)

| | F0 | P0 | CB |
|---|---|---|---|
| Unanswerables answered /18 | 5 | 13 | 18 |
| Answerables answered /52 | 43 | 47 | 51 |

- **F0 vs P0, unanswerables:** b/c 8/0, Holm p 0.023. F0 vs CB: 13/0, Holm p 0.001. The answerables tests are in `baselines_tests.csv`.
- **Robustness (found by the final advisor check):** P0 `nr3147` is a refusal written in bold, "does **not** explain", which the regex misses. Four more P0 answers reject the premise rather than give a reason. If all five count as non-answers, F0 vs P0 drops to 3 discordant (p 0.25). The scores stay as pre-registered and the report flags this. **F0 vs CB is robust.** `nr3177` (P0 "no reason stated") is a further paraphrased refusal the regex missed.

### 2. Correctness (secondary; single labeller: Clifton, blind; unadjusted; /52 answerables)

| Arm | Strictly correct | Leniently correct (correct + partial) | Wrong |
|---|---|---|---|
| F0 | 30 | 42 | 1 |
| P0 | 30 | 47 | 5 |
| CB | 0 | 3 | 49 |

- **Tests:** F0 vs P0 strict 4/4 (p 1.0), lenient 1/6 (p 0.125). F0 vs CB strict 30/0 (p 1.9e-9), lenient 40/1 (p 3.8e-11). Independently recounted by a sub-agent: all numbers match.
- **Watch out:** the correctness table's "answered" column (F0 43, P0 52, CB 52) uses **strict** scoring. Don't put it next to the lenient 47/51. Drop the column or label it "answered (strict)". `q3958` is a lenient refusal that was labelled "correct".
- **Old F0 labels vs Clifton's:** old strict 33/52 vs 30/52 now; same label on 32 of 43; kappa 0.39 over 3 labels, 0.59 for correct vs not. Goes in the limits.
- **Reading:** grounding does not raise correctness on answerables (equal with plain RAG). Its value is fewer wrong answers (1 vs 5) and fewer dishonest answers to unanswerables. CB getting 0/52 strictly correct shows the answers come from retrieval, not from the model's memory.

### 3. Post hoc tagging of answered unanswerables (must be labelled post hoc)
- **Tags:** honest (refuses / what-not-why / other), false_premise (denies a change that really happened; the premise is true by construction for both nr and rm questions), invents (invents a reason / borrows one from another MR).
- **Headline, single rater (Codex, all arms), /18:**

  | Arm | Honest | False premise | Invents | Not honest | Not honest without nr3177/nr4460 (/16) |
  |---|---|---|---|---|---|
  | F0 | 13 | 0 | 5 | **5** | 3 |
  | P0 | 6 | 2 | 10 | **12** | 11 |
  | CB | 0 | 7 | 11 | **18** | 16 |

- **Check:** James's tags on P0/CB agree with Codex on honest vs not 29/31; both give P0 12/18 and CB 18/18. Kappa is about 0 (−0.03) because of the prevalence paradox (each tagger marked one row honest), so report the raw agreement. invents vs false_premise agreement is poor (19/31, kappa 0.19), so report only the combined "not honest".
- **The 2 disagreements on honest vs not:** P0 rm584 (James honest, Codex false_premise) and P0 nr4460 (James false_premise, Codex refuses). James still has to decide them; neither changes 12/18.
- **Story:** grounding avoided a failure that plain RAG fell into. P0 often used the retrieved context to argue against a true premise or to build a reason.
- **Caveat:** a premise rejection is only false if the question is right, and the question check was mostly automated (kappa 0.177).

### 4. Gate on GitLab (exploratory, held-out)
- **F0:** unanswerables answered 5 → 2, at a cost of 1 answerable and 1 provisionally correct answer. Matches the 6 Nov run exactly.
- **P0:** the gate removes nearly everything, because P0 rarely cites and uncited answers are gated by rule.
- **For the demo and report,** use these GitLab numbers, not the old Django "301/659 kept". MiniCheck AUROC for unanswerables was near chance on Django (0.54–0.57).

### 5. Retrieval carry-through (Task 3)
- **Evidence span in context (47):** F0 answered 42; 33 correct (old provisional labels).
- **Span not in context (5):** refused 4; answered 1, wrongly.
- **GitLab H0 vs F0:** skipped, because there are no GitLab H0 generations.
- **Django:** F0 vs S0 overlap-cited 31 vs 20 of 50 (p 0.013, unadjusted), and the long-PR tertile table. Cited from `ESP3201A_Exp2/results`, not recomputed.
- **Message:** retrieval quality (Exp 1) is the main lever.

### 6. Reproducibility
- Ollama version and model digest were unchanged from F0.
- The F0 re-run was 70/70 identical, so the baselines were generated under F0's exact conditions.

## Demo app (`ESP3201A_SWE_exp1_app`)
- **Structure:** `app/server.py` (local server), `app/engine.py`, `app/static/` (vanilla JS), `app/desktop.py`, `app/final_settings.json`, and the new `app/gate.py`.
- **Commits (re-authored 12 Nov: Tze Xuan as author, Alyssa and Clifton as co-authors):** `7847a72` (baseline), `916b59d` (feedback), `4a77349` (gate). The old hashes `8c9dd76` / `b3115e0` / `fbbf7f4` no longer exist. There is no remote yet.
- **No demo is planned** (presentations are done). The only live answerable test of the support check was held back (0.04), and the pass case was tested in Python only. The README should say this; no further testing is needed.
- **Feedback loop:**
  - 👍/👎 plus a "Report" dropdown: wrong answer / invented reason / borrowed from another PR / describes what, not why.
  - Optional correct PR and comment.
  - Each click appends one line to `feedback/feedback.jsonl`, with question, answer, model, prompt version (`v3` strict / `b` standard), `final_settings` and `settings_used`, chunk ids, cited ids, gate, rating, report_type, correct_pr, comment, `reviewed: false`.
  - A failed save is shown and is harmless.
  - `feedback_summary.py` and `feedback/README.md`: the log is for human review before reuse; the app does not learn from it. The log is currently empty (0 rows).
- **Gate toggle** ("experimental support check"):
  - In Settings, off by default, and imports the Exp 2 gate unchanged (MiniCheck, cited-min, `gate_eval.THRESHOLD` 0.5).
  - Strict mode only: greyed out in standard mode with a note.
  - Refusals are not scored; uncited answers are held back as `no_citation`.
  - A held-back answer shows a message, the score, "Show anyway" and the excerpts. The answer text is never changed, and the answer isn't streamed until the check decides.
  - Timing: about 0.3 s per check; the first MiniCheck load takes about 8 s.
  - Tested held-back (0.04) and refusal live. The pass case (0.94) and no-citation case were tested in Python only, because no live answer passed.
- **Known issues:**
  - BM25 mode won't run on James's system Python (nltk, rank-bm25, fastembed and datasets are missing); the final dense setup works.
  - Ollama output varies slightly between runs even at temperature 0 with seed 42.
  - A "demo-app" entry was added to `ESP3201A/.claude/launch.json`; the old "pr-explainer" entry points to a Python environment that no longer exists.
- **Report framing:** the feedback loop is infrastructure for learning from human checks, presented as design and future work. It closes a loop that is currently one-way. Possible uses later: regression tests, gate calibration, retrieval tuning (via correct_pr), and preference pairs for steering or DPO. Never claim the app learns. User labels are noisy (kappa 0.177 / 0.39).

## GitHub
- **No repo exists yet.** Neither local repo has a remote.
- **The submission repo needs code from:**
  - the Exp 1 folders (Clifton's; `ESP3201A_SWE_exp1_app` contains the Exp 1 code + app);
  - `ESP3201A_Exp2`;
  - `gitlab_runner_copy`.
- **Leave out:** `emb_cache/`, `prs/`, `chunks/`, `qdrant*`, `keys/`, `feedback/*.jsonl`.
- **Description drafted in chat on 12 Nov:**
  - Title: "Why Was This Changed? A Local, Grounded RAG Assistant for Code Review History".
  - About: *Local, offline RAG assistant that answers "why was this code changed?" from GitHub PRs and GitLab MRs, with citations or an honest "not found". Evaluated on Django, SymPy and GitLab Runner.*
  - The SymPy headline numbers are still missing from that description.

## Still to do
1. **Decide** the two honest-vs-not disagreements (P0 rm584, nr4460) and record the decision.
2. **Choose the master copy** (OneDrive vs `ESP3201A_local`), merge `exp2-baselines`, rebuild and send the bundle to Clifton. The existing zip predates the correctness and tagging results.
3. **Write the report draft,** by about 22:00 Thu. Section order: baselines → correctness → tagging (post hoc) → gate → carry-through → steering → app/feedback → limits.
   - Pre-registered vs exploratory vs post hoc must be explicit.
   - Steering is activation steering: never RL or fine-tuning.
   - **Limits:**
     - 70 questions from 1 repo, with provisional and partly automated question checks (kappa 0.177);
     - a single correctness labeller, and old-vs-new kappa 0.39;
     - 18 unanswerables, so low power;
     - doubtful nr3177/nr4460 labels;
     - a broad regex plus missed paraphrased refusals;
     - the P0 citation-stripping blinding leak (11 answers left "()" traces);
     - one seed; Ollama run-to-run variation;
     - Claude-written gold answers.
4. **Build the GitHub repo:** layout, `.gitignore`, README with the description, real authors, push.
5. **The 87-row F0/C1 second labelling** (`exp2_gitlab_A2000/correctness_sheet_blank.csv`): only if time remains; Clifton's sheet already re-labels F0.
6. **Update `HANDOVER.md`** in `gitlab_runner_copy` (nice to have).

## Standing rules (unchanged)
- Never run `exp2_gitlab_scale.py score` or `build`.
- Never edit Exp 1 files, existing results or label files; commit before every run.
- Labels and tags are made by humans; an AI rater is only a check, and is labelled as such.
- Nobody opens a `keys/` folder until the labels are final.
- Tokens go in the terminal only.
