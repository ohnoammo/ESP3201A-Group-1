"""Load SWE-bench Verified tasks for one repository (Experiment 1, code review).

    load_dataset("princeton-nlp/SWE-bench_Verified", split="test")  -> 500 tasks
    repo == "django/django" -> 231 tasks (sympy 75, sphinx 44, ...)

Each task: the bug report (problem_statement) is the QUERY, the fixing pull request is the
correct answer. The PR number is the number at the end of instance_id
(e.g. "django__django-11099" -> PR #11099).
"""
import re
from datetime import datetime

DATASET = "princeton-nlp/SWE-bench_Verified"


def to_ts(iso):
    """'2019-03-17T21:43:12Z' -> epoch seconds (float)."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def short_query(text):
    """First non-empty line of the bug report (the optional 'short query' set)."""
    return next((line.strip() for line in text.splitlines() if line.strip()), text.strip())


def patch_files(patch):
    """File paths changed by a unified diff (from its 'diff --git a/X b/X' headers)."""
    return sorted(set(re.findall(r"^diff --git a/(\S+) b/", patch, flags=re.M)))


def load_swebench(repo="django/django", dataset=DATASET, split="test"):
    from datasets import load_dataset          # Hugging Face download (cached after first run)
    rows = []
    for r in load_dataset(dataset, split=split):
        if r["repo"] != repo:
            continue
        m = re.search(r"-(\d+)$", r["instance_id"])
        if not m:
            raise ValueError(f"no PR number at the end of {r['instance_id']}")
        rows.append({
            "instance_id": r["instance_id"],
            "repo": r["repo"],
            "pr_number": int(m.group(1)),
            "problem_statement": r["problem_statement"],
            "short_query": short_query(r["problem_statement"]),
            "patch": r["patch"],
            "test_patch": r["test_patch"],
            "patch_files": patch_files(r["patch"]),
            "created_at": r["created_at"],
            "created_ts": to_ts(r["created_at"]),
        })
    rows.sort(key=lambda t: t["instance_id"])
    return rows


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="django/django")
    a = ap.parse_args()
    tasks = load_swebench(a.repo)
    print(f"{a.repo}: {len(tasks)} tasks; PR numbers {min(t['pr_number'] for t in tasks)}"
          f"-{max(t['pr_number'] for t in tasks)}; dates {min(t['created_at'] for t in tasks)}"
          f" .. {max(t['created_at'] for t in tasks)}")
