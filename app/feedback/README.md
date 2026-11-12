# Feedback log

`feedback.jsonl` is written by the demo app (`POST /api/feedback` in `app/server.py`) when someone
clicks 👍 / 👎 or sends a report under an answer. Each click or report appends one JSON line. The
file stays on this computer and is git-ignored.

**The app does not learn from this log.** Nothing in the app reads it back: retrieval, prompts,
settings and answers are unchanged by anything recorded here.

**It is for human review before any reuse.** A row is a user's opinion, not a label. Before a row
is used for anything (a regression test, calibrating an answer gate, or a preference pair), a
person should check it against the PR and set `"reviewed": true`. Rows with `"reviewed": false`
should not be reused.

## Fields

| field | meaning |
|---|---|
| `ts` | local time the row was saved |
| `question`, `answer` | the question and the model's full answer |
| `model`, `mode`, `prompt_version` | Ollama model; `strict` (prompt v3) or `standard` (prompt b) |
| `final_settings` | `app/final_settings.json` at save time |
| `settings_used` | settings the UI actually used for this answer (may differ from final) |
| `context_chunk_ids` | chunks given to the model, in context order |
| `cited_ids` | excerpt ids the answer cites, e.g. `PR1234-c0` |
| `gate` | experimental support check: `null` when the toggle was off; otherwise `status` (`scored` / `not_scored_refusal` / `error`), `score`, `threshold`, `passed`, `held_back_reason` (`low_score` / `no_citation`) and `seconds` |
| `rating` | `up`, `down` or `null` |
| `report_type` | `wrong_answer`, `invented_reason`, `borrowed_from_other_pr`, `what_not_why` or `null` |
| `correct_pr`, `comment` | optional free text from the user |
| `reviewed` | `false` until a person has checked the row |

## Counts

    python feedback_summary.py

prints thumbs up/down, report-type counts and the number of rows not yet reviewed.
