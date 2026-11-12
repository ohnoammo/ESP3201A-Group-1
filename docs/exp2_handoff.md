# Exp 2 handoff (ESP3201A local RAG project), as of 23 Oct 2026, 03.00 SGT

Supersedes the Exp 2 section of `claude/exp1_handoff.md`. Exp 1 parts of that file are out of date (pool A changed, relation factor added).

## How this chat works
- James owns Experiment 2 (generation / faithfulness). Teammates Clifton and Alyssa own Experiment 1 (retrieval).
- Claude Code does the work on James's machine (RTX 5070 12 GB). James pastes its reports here. This chat critiques them, catches problems, and writes paste-ready instructions for Claude Code.
- Push back where the reports are wrong or over-claimed. Keep differences of 1 to 3 questions labelled as noise.

## Project in one paragraph
Offline RAG over code review history. Corpus is Django GitHub PRs (from SWE-bench Verified tasks), one PR = one document (title/description, commits, diff hunks, review threads, conversation comments). Exp 1 asks which chunking and retrieval find the right PR and chunk. Exp 2 asks whether a local LLM answers "why was this changed?" questions faithfully, and says "Not found" when the reason isn't there. Interim was 16 Oct. Group has decided to target GitLab for deployment (test on GitHub first).

## Prof feedback (16 Oct) and how it's handled
| Comment | Handling |
|---|---|
| "Relation factor" for long PRs | Defined by the group as links between chunks, scored by rank. Exp 1 does code links, Exp 2 does explanation links |
| Failure analysis | Planned for both experiments (not yet done for Exp 2 test arms) |
| AI to suggest code fixes | Future work |
| GitHub online vs local; platform issue | GitLab target. Design write-up. Commit as base layer, PR/MR/ticket as enrichment, read-only mirror + incremental indexing |
| Varied languages, no PRs elsewhere | Limitation (Django = Python). Commits-only ablation still to do |

## Exp 1 state that Exp 2 depends on
- Latest Exp 1 code is in `ESP3201A_SWE_exp1_2210` (OneDrive). Exp 2 runs from a copy outside OneDrive at `C:\Users\kwekt\ESP3201A_local\exp1_copy`.
- Pool A was updated (same-ticket filter swapped 16 distractors). Exp 2 now uses the new pool. Tier 2/3 results below are from the OLD pool with top-5 contexts.
- `relations.py` (`expand_and_pack`, `token_counter`). Rank-based scoring. Retrieved chunk = 1/rank, linked chunk = alpha / rank of the chunk that pulled it in. Budget 2,560 in Exp 1's word-and-symbol unit. Group safety rule. alpha > 0 only if the answer PR stays in budget at most 0.02 less often than alpha 0.
- Exp 1 alpha picks (code links, line recall). dense fixed 1, structural 0.5. Exp 1 also has a hard pool H (not used by Exp 2).
- `retrieve.py`, `hard_pool.py`, `check_leakage.py` are not in the 2210 folder. Exp 2 still uses `retrieve.py` from the copy. Asked the group whether that was deliberate (no answer recorded).

## Exp 2 setup
- Folder `ESP3201A_Exp2/` (git). Has `HANDOVER.md` written by Claude Code.
- Model under test. `qwen3:4b-instruct-2507-q4_K_M` (plain `qwen3:4b` is a thinking-only build) and `qwen3:8b`. Also ran `qwen3:4b-q4_K_M` (original hybrid) in Tier 3. Ollama 0.40.4, auto-update OFF, temp 0, seed 42, num_ctx 8192. Version guard in the runner.
- Retriever. Dense Qwen3-Embedding-0.6B with an Exp 2 "why" query instruction. Packing through Exp 1's `expand_and_pack` via the wrapper `pack_exp1.py`.
- Exp 2 link types. hunk <-> mapped review thread (35% of threads map to a hunk), every part -> title+description, conversation comment <-> previous/next comment by date. Their "context" link type did nothing on why questions (only links from hunks).

### Question sets (all Claude-generated, verbatim quote checks, copy check < 6 shared words)
- Test. 50 answerable + 5 no-reason (test) + 5 no-reason (dev, from pilot) + 5 removed cases.
- Dev-2 (for tuning only). 40 answerable (23 review-thread answers, deliberately skewed) + 5 no-reason, from unused shortlist PRs, no shared tickets with test.
- James hand-checked all test priority rows and all 45 dev-2 rows. Codex (GPT) independently reviewed both sets. Quotes widened to multi-span where gold exceeded the quote.
- Removed cases come in two variants. "Whole PR excluded" (n = 5). "Answer removed, PR kept" (redacted documents, group leakage rule). rm13671, rk12342 and rk11459 dropped from "PR kept" because the remaining text still gives the reason away. Report "PR kept" as case studies only.
- 8 of 15 no-reason questions link an external ticket (12 cite a ticket number). The reason often lives in Trac, not the PR. Argument for indexing the issue tracker as an enrichment layer.

### Prompts
- (a) no retrieval, (b) standard RAG, (c) strict grounded (answer only from context, cite chunk, else "Not found in the provided PRs").
- Grounded v2 frozen. v3 adds "describing WHAT changed is not a reason WHY". v3 frozen as drafted. Both run on test as a factor.

### Tuning on dev-2 (committed rule before running)
- Fixed alpha 0 (links rejected by the safety rule by exactly 1 question, fragile; report as "no reliable benefit").
- Structural alpha 0.25.

## Findings so far
### Tier 2/3 (old pool, top-5 contexts, auto-scored)
- Grounded prompt abstains when evidence is missing (retrieval miss, removed PR) but often invents a reason when the PR is present and simply gives none.
- 8B abstains least. Under grounded, 8B answered 8 of 10 unanswerable cases. Failure modes. borrowing from neighbouring PRs with valid-looking citations, describing WHAT as WHY, and (hybrid 4B) bare citations with no answer text (now scored as empty).
- Closed-book rule. Per model, answerable questions answered correctly with no retrieval are flagged, and retrieval benefit is reported with and without them (q9540, q14989 checked, all models wrong or near-miss closed-book).

### Retrieval-level relation factor (test, 2,560 budget)
- Structural ~= fixed for answer-in-context (0.86 vs 0.84). Exp 2 links on structural peak 0.90 at alpha 0.5, within noise. On fixed, links only hurt. Most misses are the answer PR not retrieved at all, which links cannot fix.
- Dev-2 answer-in-context at alpha 0. fixed 0.725, structural 0.825.

### Final test arms (new pool, packed contexts, auto-scored, correctness NOT yet judged)
Arms F0 (fixed, alpha 0), S0 (structural, alpha 0, score order), S0-G (structural, alpha 0, grouped by PR in document order), S-0.25 (structural, alpha 0.25, grouped), each x prompt v2/v3, x 4B-instruct and 8B. 552 rows per model.
- Model matters more than prompt. v3 helps 4B abstain (F0 no-reason test 1 -> 4, dev up to 5/5 on S0-G). 8B is 0/5 on dev no-reason in every arm whatever the prompt.
- v3 costs coverage. Abstaining although the answer span was in context doubles on 4B structural (6 -> 12).
- Context shape matters even at equal retrieval. All arms have the answer span in context 42-44/50, but structural (~15 PRs in context) has lower citation precision (~0.6 vs ~0.85 for fixed) and more borrowing on 8B (up to 4 vs 1). This is the prof's "context loss" at generation level. Counts are small, call it a trend.
- Grouping (S0-G) and alpha 0.25 help slightly. Best structural arm 4B S-0.25 v3 (32 right chunks, precision 0.73). Within noise.
- 8B borrows in removed cases (rm16129 -> #12646, rm12342 -> #13507).
- q14748 has no single structural chunk with its full quote (partial overlap only).

## Decisions made (do not reopen without reason)
- Exp 2 uses the new pool A, `expand_and_pack`, 2,560 budget, rank-based alpha.
- No pool H for Exp 2. No SWE-bench download.
- Prompt factor v2 vs v3 both reported, v3 frozen as is.
- nr10042, dnr8827, dnr9477 stay "Not found" (PR-only evidence).
- q12441 gold trimmed (option a). rm14349 retired 15 Oct.

## To do (in order)
1. Claude Code to apply the latest decisions (drops from "PR kept", correctness pack, MiniCheck, stats). See the Claude Code prompt.
2. Correctness. Codex (GPT) as blind judge on answered answerable rows against gold. MiniCheck-Flan-T5-Large (HHEM-2.1-Open cross-check) for faithfulness against cited chunks and full context. James hand-labels a ~80-row fixed-rule stratified sample to measure agreement.
3. Paired McNemar tests on the 50 test answerables for F0 vs S0, S0 vs S0-G, S0-G vs S-0.25, v2 vs v3 within arms.
4. Failure analysis table with one example per category (retrieval miss, wrong chunk, same-ticket, invented reason, what-as-why, borrowing, bare citation, over-abstention).
5. Commits-only ablation (strip PR description and discussion, keep commit messages + diffs).
6. GitLab question set and adapter (later, after GitHub results are final).
7. Report write-up. Platform design table (live connection vs upload vs read-only mirror + incremental index), change-record schema, limitations.

## Caveats to state in the report
- Questions and gold written by Claude; checked by James and Codex.
- n = 5 per abstention category; "PR kept" is case studies only.
- Dev-2 skewed to review-thread answers.
- Non-determinism at temp 0 (wording varies, outcomes did not flip in checks).
- 4B-instruct vs 8B differ in generation as well as size.
- BM25 untuned, Django/Python only, PR-only evidence (tickets excluded).
