# Failure analysis (queue c; approved 1 Nov)

Generated from `results/failure_examples.json` (`failure_examples.py`). Rows: 2 models x 4 arms x 2 prompts
x 67 questions = 1,072 (50 answerable test + 17 unanswerable; dropped rk11459/rk12342 left out).
Answered = not abstained (strict rule) and not empty. Codex labels for answerable rows.

**Selection rule (every category).** Candidates sorted by (model, arm in F0/S0/S0-G/S-0.25 order, prompt,
question id); take the first whose question id is not already used in the table. Categories are filled in
table order. No hand-picking. If every candidate question is already used, the first candidate is shown and
marked as a repeat. Alyssa-tag categories use her 10-row gate-pass sample
(`judgements/gate_pass_sample_alyssa.md`, main tag = first word of the tag); Clifton's file is not used.

| category | rule | candidates (rows) | example id | model / arm / prompt | one-line explanation | count / denominator | source |
|---|---|---|---|---|---|---|---|
| retrieval miss | answerable, gold PR not in context, answered | 15 (3 questions) | q10177 | 4B / S-0.25 / v2 | Gold PR absent. Answers from PR 16417 ("only 2% of survey respondents use Oracle"). Gold: the flag already existed. Codex wrong. | answered 15 / 44 answerable rows with gold PR not in context; abstained 29 / 44 | rule-selected |
| wrong chunk | answerable, gold PR in context, answered, >= 1 citation, no cited chunk overlaps a gold span, Codex wrong | 56 (16 questions) | q14503 | 4B / F0 / v2 | Cites its own PR, but not the gold chunk. Says the check "was already implicitly handled"; gold says such tags already crash. | 56 / 644 answered answerable rows with gold PR in context | rule-selected |
| same-ticket | answered, cites a PR that shares a ticket with the question's PR (pool A, ticket ids from titles) | 2 (1 question) | q15435 | 8B / S0 / v2 | Cites PR 15423 (same ticket, earlier attempt): "prevented LazyObject from mimicking nonexistent attributes". Gold: `__getattribute__` skipped LazySettings' `__getattr__`. Codex partial. | 2 / 800 answered rows (answerable + 17 unanswerable) | rule-selected |
| invented reason | Alyssa's tag "invented" | 5 (3 questions) | nr9172 | 4B / F0 / v3 | No reason in the PR. Answer adds "to ensure data consistency" and "match expected behaviour", which are not in the chunk. Passes the gate (MiniCheck 0.930). | 5 rows in Alyssa's 10-row gate-pass sample (nr10075 is 5 of the 10); not a rate | Alyssa tag |
| what-as-why | Alyssa's tag "what-as-why" | 3 (3 questions) | nr10042 | 4B / F0 / v2 | No reason in the PR. Restates the title ("silence them in the default verbosity") as the reason, plus "cleaner output". | 3 rows in Alyssa's 10-row gate-pass sample (nr10075 is 5 of the 10); not a rate | Alyssa tag |
| borrowing | Alyssa's tag "borrowed" | 2 (2 questions) | nr10075 | 4B / S0 / v3 | No reason in the PR. Takes the UnicodeDecodeError reason from PR 11640's commit message. Both judges call it supported (MiniCheck 0.737, HHEM 0.872). | 2 rows in Alyssa's 10-row sample; by rule 60 / 798 answered rows with >= 1 citation cite no chunk of the question's PR | Alyssa tag |
| bare citation | >= 1 citation and < 3 words after removing citations | 2 (1 question) | nr9172 | 4B / S0 / v3 | Answer is only `[PR9172-c0]` (the other row, S0-G/v3, is only `[PR9172-c2]`). Same question as the invented-reason example; the only candidate question (2 rows). | 2 / 1,072 rows | rule-selected (repeat) |
| over-abstention | answerable, abstained, answer span in context | 70 (22 questions) | q12441 | 4B / F0 / v2 | Refuses ("Not found in the provided PRs") although the gold span (ErrorList subclasses UserList) is in context. q16824 is a candidate (4 rows) but is not the one picked. | 70 / 688 answerable rows with answer span in context | rule-selected |

The categories are not exclusive: the retrieval-miss example (cites only PR 16417) and the same-ticket
example (cites only PR 15423) also count as borrowing under the rule. So counts do not sum, and each count
names its own population.

Notes:
- Bare-citation rows are empty answers, so they count as non-answers and were never judged.
- Pool A's same-ticket filter covered only Exp 1's fixing PRs. 10 of the 50 answerable gold PRs still have
  a same-ticket PR in the pool (8934, 9789, 11459, 12342, 13671, 14624, 14989, 15435, 16129, 16559). Only
  q15435 has same-ticket citations (8B S0, v2 and v3). See the limitation in `exp2_results_tables.md`.
- The invented-reason and bare-citation example nr9172 is one of the two "clued" no-reason questions (P3).
