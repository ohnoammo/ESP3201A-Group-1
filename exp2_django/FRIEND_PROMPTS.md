# Prompts for continuing Experiment 2

Two prompts: one for **Claude Code** (does the work in the repo), one for a **side chat** (advisor that critiques Claude Code's reports and writes its next instructions). Replace `<NAME>` with your name.

Before starting, copy the whole `ESP3201A_Exp2/` folder (including `.git`, `judging/`, `reviews/`, `results/`) and the Exp 1 copy (`C:/Users/kwekt/ESP3201A_local/exp1_copy`, which holds the PR data and cached embeddings) to your machine. Also send the advisor chat `exp2_handoff.md` and `HANDOVER.md` as attachments.

---

## 1. Claude Code prompt (paste as the first message in the `ESP3201A_Exp2` folder)

```
I'm <NAME>, taking over Experiment 2 of our ESP3201A project from James (generation/faithfulness of
a local LLM answering "why was this changed?" questions about Django PRs). Exp 1 (retrieval) is
owned by Clifton and Alyssa. I'm on a different machine from James.

Read first, in this order, before doing anything:
1. HANDOVER.md (rules, frozen setup, decisions, findings, queue). Its rules are binding; where it
   says "James", read "<NAME>" for decisions, but James's label files stay untouched.
2. tuning_rule_dev2.md, tuning_rule_gate.md
3. results/exp2_results_tables.md
4. reviews/methods_review_codex.md
5. results/run_provenance.md
6. judging/codex_instructions.md

Then, before running anything, do a setup check and report it:
- Paths: HANDOVER/common.py point at C:/Users/kwekt/... . Find every hard-coded path, tell me what
  needs changing for my machine, and propose one config change (don't edit Exp 1 files).
- Ollama version must be 0.40.4 with auto-update off; models qwen3:4b-instruct-2507-q4_K_M and
  qwen3:8b. Report what I have and my GPU/VRAM.
- git status and latest commit; confirm it matches HANDOVER "State (24 Oct)" (d816b67 or later).
- Re-run one cheap determinism check (e.g. regenerate 3 existing test-arm rows, or rescore
  score.py on an existing gen file) and compare to the committed outputs. Different hardware may
  change outputs: if anything differs, stop and tell me — don't regenerate anything.

Hard rules (repeat of HANDOVER, don't break them):
- Never tune on test. Commit before every run; every result row records config, alpha, budget,
  prompt version, Ollama version, git commit (add machine/GPU now that there are two machines).
- Prompts and arms are frozen. Never open judging/keys/ while labels are pending.
- Never overwrite review_sheet.csv, review_priority_v2.csv, review_dev2.csv, validation_sample.csv.
- Never edit Exp 1 files.

Work the HANDOVER queue in order (a: finish PR-length/fit analysis + draft tuning_rule_wholepr.md,
then STOP before generation; b: correctness once the 80 validation labels exist; c: failure
analysis; d: demo only after group confirms; e: final tables). Stop at every checkpoint.

Reporting: results, not process. One status line, one table, at most 3 issue bullets, then
"Decision needed:" only if it really is mine. ~150 words max excluding tables. I'll paste your
reports into an advisor chat, so make them self-contained. Keep HANDOVER.md updated at the end of
every session (state, decisions with dates, queue).
```

---

## 2. Advisor side-chat prompt (claude.ai; attach `exp2_handoff.md`, `HANDOVER.md`, `results/exp2_results_tables.md`)

```
I'm <NAME>, taking over Experiment 2 of our ESP3201A group project (offline RAG over Django PR
review history) from James. The attached exp2_handoff.md, HANDOVER.md and exp2_results_tables.md
describe the project, the frozen setup, decisions so far, findings and the remaining queue.

How this chat works:
- Claude Code does the work on my machine. I paste its reports here.
- Your job: critique each report, catch methodological problems, and write paste-ready
  instructions for Claude Code's next step (in a code block, self-contained).
- Push back when a report is wrong, over-claims, or quietly breaks a rule. Differences of 1–3
  questions out of 50 are noise; say so. Nothing is "significant" unless it survives Holm in
  its pre-declared family.
- Guard the rules: no tuning on test; prompts/arms frozen; rule files committed before results;
  blind judging keys unopened; James's review/label files never overwritten; Exp 1 untouched.
- I'm on a different machine (different GPU, maybe different paths). Treat any change in
  generation outputs vs James's committed runs as a reproducibility issue to report, not
  something to silently re-run.
- Keep a running state at the end of each reply: queue position, open decisions, what's waiting
  on others (James's 80 validation labels, group demo plan).

Start by: (1) summarising in ≤10 lines where Exp 2 stands and what's next, (2) listing anything
in the handoff you think is risky or unclear that I should ask James before he's gone, and
(3) giving the first instruction for Claude Code (setup check on my machine, then queue item a).
```
