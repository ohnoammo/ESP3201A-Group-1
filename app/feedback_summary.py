"""Count what is in the demo app's feedback log.

    python feedback_summary.py [path]      (default: feedback/feedback.jsonl)

Prints thumbs up/down, report-type counts and how many rows are not yet reviewed.
Read-only: it never changes the log. See feedback/README.md.
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT_TYPES = ["wrong_answer", "invented_reason", "borrowed_from_other_pr", "what_not_why"]


def main(path):
    if not os.path.exists(path):
        print(f"No feedback yet ({path} does not exist).")
        return
    rows, bad = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                bad += 1
    ratings = collections.Counter(r.get("rating") for r in rows)
    reports = collections.Counter(r.get("report_type") for r in rows if r.get("report_type"))
    print(f"Feedback log: {path}")
    print(f"Rows: {len(rows)}" + (f"  ({bad} unreadable lines skipped)" if bad else ""))
    print(f"Thumbs up:   {ratings['up']}")
    print(f"Thumbs down: {ratings['down']}")
    print("Reports:")
    for t in REPORT_TYPES + sorted(set(reports) - set(REPORT_TYPES)):
        print(f"  {t:<24} {reports[t]}")
    print(f"With a correct PR given: {sum(1 for r in rows if r.get('correct_pr'))}")
    print(f"With a comment:          {sum(1 for r in rows if r.get('comment'))}")
    print(f"Not yet reviewed: {sum(1 for r in rows if not r.get('reviewed'))}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "feedback", "feedback.jsonl"))
