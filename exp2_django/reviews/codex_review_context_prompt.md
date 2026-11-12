Context from a separate session: an independent Codex review of review_priority_v2 (Exp 2, ESP3201A_Exp2). Use this when updating review_sheet.csv / the question set. Nothing in the project was edited except adding `codex_review_v2.md` (Codex's full row-by-row review).

## How the review was done
- Codex (OpenAI Codex CLI, high reasoning effort, read-only) reviewed all 75 rows of review_priority_v2.
- Inputs were generated from the project code: full PR text (`common.doc`) for each row's PR, digests of retrieved PRs for test no_reason rows, and the text of the 5 retrieved chunks for each removed (rm) row.
- Codex saw only the questions first and wrote its own answers before opening the gold answers, quotes, Claude's notes and existing decisions.
- Result: 60 keep, 15 fix, 0 drop. It agreed with 13 of the 19 existing decisions.

## Decisions agreed with James after checking
1. **nr10042: keep (Codex said fix; overruled).** The PR title "Silenced post-process messages in collectstatic's default verbosity" states WHAT changed, not WHY. The reason is only in the external Trac ticket #29464. "Not found" stays correct.
2. **rm12342: keep, no leakage.** All 5 retrieved chunks are from PR #13507 (alias order / `default` first for data migrations). None says that tests should use only `cls.databases`, or that looping over all connections would cause errors if more databases are added.
3. **q9540 and q14989: keep.** Codex worried that both could be answered from general knowledge (cookie prefixes; asyncore/smtpd deprecated in Python 3.10). Checked against `results/gen_test_4b-instruct.jsonl` and `gen_test_4b-hybrid.jsonl`: in the no-retrieval condition (none:a), BOTH 4B models got BOTH wrong.
   - q9540: they said the secure flag is there because these cookies are "transmitted only over HTTPS". They never mention browsers ignoring the Set-Cookie header.
   - q14989: they said the modules were "not reliable/efficient" or "not available". Neither mentions the 3.10 deprecation.
   - With retrieved or full-PR (oracle) context, both models answered correctly.
   - So both questions still distinguish answers taken from the PR. Mention this check in the report. Caveat: re-check the 8B's no-retrieval answers for these two before relying on them in the size comparison.

## Other Codex findings (not yet decided by James)
**Disagreements with existing "keep" decisions (all evidence or wording fixes, answers judged correct):**
- rm11459 / q11459: quote omits the `%d` reason and the Python 3 explanation (why an integer is suitable, why a float was used).
- rm16129 / q16129: gold includes the customization rationale; the selected quote does not.
- q16966: answer right; the quote should include the timing evidence.
- q11377: quote supports only part of the gold; include the `repr()` and copy/pasteability lines.
- q14727: quote supports only the general messaging point, not the specific case and remedy.
- q8930: "is one mutable object" is awkward; say the instances share the mutable default.

**Agrees with existing "fix" decisions:**
- q8934: keep the author's stated uncertainty in the gold.
- q14349: use the fuller explanation of `urllib.parse()` stripping characters.
- q13680: say psycopg2 would quote the identifiers, so they can't be read as SQL expressions.

**Undecided rows Codex marked fix (gold says more than its quote):**
- q15251: gold adds a flex-layout reason the quote doesn't establish.
- q14624: trim the gold to the uncertainty actually stated.
- q14142: the answer includes CI slowdown and possible swapping; cite the fuller discussion.
- q11283: the extra claim about refusing the migration needs its own quote.

**Main pattern:** about 10 gold answers go beyond their selected quote (rm11459, rm16129, q11377, q14349, q14624, q14727, q15251, q16129, q14142, q11283). These are mostly fixed by widening the quote; the answers themselves look right.

All other rows: Codex says keep. Full per-row answers, evidence and reviewer questions are in `codex_review_v2.md`.
