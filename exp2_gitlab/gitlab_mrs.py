"""GitLab adapter: saves merge requests in the same JSON shape github_prs.fetch_pr writes, so the
Exp 1 document, chunking and retrieval code runs on them unchanged. number = the MR iid.

  python gitlab_mrs.py index                             list every merged MR (no diffs)
  python gitlab_mrs.py pool --tasks 30 --distractors 270 choose tasks + distractors, download

Mapping: description -> body; DiffNote discussions -> review_comments (path + new line);
other non-system notes -> issue_comments; system notes dropped; bots by username (GitLab's public
API has no user type). Token optional: GITLAB_TOKEN (never passed on the command line).
Tasks (Exp 1 labels): an MR whose description closes a public issue of the same project, where the
issue was opened before the MR and has at least MIN_ISSUE_WORDS words. Fixed SHA-256 order, seed 42.
"""
import argparse
import hashlib
import json
import os
import re
import time
from urllib.parse import quote

import requests

REPO = "gitlab-org/gitlab-runner"
API = f"https://gitlab.com/api/v4/projects/{quote(REPO, safe='')}"
DIR = os.path.join("prs", REPO.replace("/", "_"))
MIN_ISSUE_WORDS = 20
PACE = 0.7                                             # seconds between requests (about 85 a minute)
BOT = re.compile(r"(^|[-_])bot($|[-_])|^gitlab-?bot$|renovate|dependabot|^gitlabduo$|^gitlab-duo", re.I)
CLOSING = re.compile(r"\b(?:close[sd]?|closing|fix(?:e[sd]|ing)?|resolve[sd]?|resolving|implement(?:s|ing)?)\b:?\s+"
                     r"(?:https://gitlab\.com/gitlab-org/gitlab-runner/(?:-/)?issues/|gitlab-org/gitlab-runner#|#)(\d+)", re.I)
MENTION = re.compile(r"(?:gitlab-org/gitlab-runner/(?:-/)?issues/|gitlab-org/gitlab-runner#|(?<![\w/])#)(\d+)")


class GitLab:
    def __init__(self):
        self.s = requests.Session()
        tok = os.environ.get("GITLAB_TOKEN")
        if tok:
            self.s.headers["PRIVATE-TOKEN"] = tok
        self.n = 0
        self.last = 0.0

    def get(self, url, params=None, tries=8, denied_ok=False):
        for attempt in range(tries):
            wait = min(120, 2 ** (attempt + 1))
            try:
                time.sleep(max(0, self.last + PACE - time.time()))   # steady pace, under the limit
                self.last = time.time()
                r = self.s.get(url, params=params, timeout=60)
            except requests.RequestException as e:
                print(f"  network error {e.__class__.__name__}; retry in {wait}s", flush=True)
                time.sleep(wait)
                continue
            self.n += 1
            rem = r.headers.get("RateLimit-Remaining")
            if r.status_code == 429 or (rem is not None and int(rem) < 10):
                pause = int(r.headers.get("Retry-After") or
                            max(5, int(r.headers.get("RateLimit-Reset", time.time() + 60)) - time.time() + 2))
                print(f"  rate limit (remaining {rem}, limit {r.headers.get('RateLimit-Limit')}); "
                      f"sleeping {pause}s until {time.strftime('%H:%M:%S', time.localtime(time.time() + pause))}", flush=True)
                time.sleep(pause)
                if r.status_code == 429:
                    continue
            if r.status_code >= 500:
                time.sleep(wait)
                continue
            if r.status_code in (401, 403):               # never read a refusal as "no data"
                if denied_ok:
                    return None, r
                raise SystemExit(f"GitLab refused {url} ({r.status_code}): set GITLAB_TOKEN (read_api)")
            if r.status_code == 404:
                return None, r
            r.raise_for_status()
            return r.json(), r
        raise RuntimeError(f"giving up on {url}")

    def paginate(self, url, params=None):
        out, page = [], 1
        while True:
            data, r = self.get(url, dict(params or {}, per_page=100, page=page))
            if not data:
                return out
            out += data
            nxt = r.headers.get("X-Next-Page")
            if not nxt:
                return out
            page = int(nxt)


def user(u):
    login = (u or {}).get("username") or ""
    return {"login": login, "type": "Bot" if (u or {}).get("bot") or BOT.search(login) else "User"}


def patch_of(f):
    d = f.get("diff") or ""
    i = d.find("@@")
    return d[i:] if i >= 0 else None


def status_of(f):
    return ("added" if f.get("new_file") else "removed" if f.get("deleted_file")
            else "renamed" if f.get("renamed_file") else "modified")


def fetch_mr(gl, n):
    base = f"{API}/merge_requests/{n}"
    d, _ = gl.get(base)
    if d is None:
        return {"number": n, "not_found": True}
    files = gl.paginate(f"{base}/diffs")
    commits = gl.paginate(f"{base}/commits")
    review, conv = [], []
    for disc in gl.paginate(f"{base}/discussions"):
        notes = [x for x in disc.get("notes", []) if not x.get("system")]
        if any(x.get("type") == "DiffNote" or x.get("position") for x in notes):
            root = notes[0]["id"]
            for x in notes:
                p = x.get("position") or (notes[0].get("position") or {})
                review.append({"id": x["id"], "in_reply_to_id": None if x["id"] == root else root,
                               "user": user(x.get("author")), "body": x.get("body"),
                               "path": p.get("new_path") or p.get("old_path"), "diff_hunk": None,
                               "line": p.get("new_line"), "original_line": p.get("old_line"),
                               "created_at": x.get("created_at")})
        else:
            conv += [{"id": x["id"], "user": user(x.get("author")), "body": x.get("body"),
                      "created_at": x.get("created_at")} for x in notes]
    conv.sort(key=lambda c: c["created_at"] or "")
    return {"number": n, "repo": REPO, "title": d.get("title"), "body": d.get("description"),
            "state": d.get("state"), "merged": d.get("state") == "merged", "user": user(d.get("author")),
            "created_at": d.get("created_at"), "closed_at": d.get("closed_at"),
            "merged_at": d.get("merged_at"),
            "commits": [{"sha": c["id"], "message": c.get("message"), "author": c.get("author_name")}
                        for c in reversed(commits)],      # API is newest first; GitHub oldest first
            "files": [{"filename": f["new_path"], "status": status_of(f),
                       "previous_filename": f["old_path"] if f.get("renamed_file") else None,
                       "additions": None, "deletions": None, "patch": patch_of(f)} for f in files],
            "files_truncated": False,
            "missing_patches": [f["new_path"] for f in files if patch_of(f) is None],
            "review_comments": review, "issue_comments": conv, "comments_fetched": True,
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(path + ".tmp", path)


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_index(gl):
    rows = gl.paginate(f"{API}/merge_requests", {"state": "merged", "order_by": "created_at", "sort": "asc"})
    keep = [{"iid": m["iid"], "title": m["title"], "description": m.get("description") or "",
             "created_at": m["created_at"], "merged_at": m["merged_at"],
             "author": (m.get("author") or {}).get("username"), "notes": m.get("user_notes_count")}
            for m in rows]
    save(os.path.join(DIR, "_index.json"), keep)
    print(f"{len(keep)} merged MRs; {sum(bool(CLOSING.search(m['description'])) for m in keep)} "
          f"name a closing issue; {gl.n} requests")


def order(rows):
    return sorted(rows, key=lambda m: hashlib.sha256(f"42:{m['iid']}".encode()).hexdigest())


def download(gl, numbers):
    for n in numbers:
        p = os.path.join(DIR, f"{n}.json")
        if not os.path.exists(p) or not load(p).get("comments_fetched", load(p).get("not_found")):
            save(p, fetch_mr(gl, n))                  # also replaces files saved without comments
            print(f"  {time.strftime('%H:%M:%S')} MR {n} saved, {gl.n} requests", flush=True)


def usable(n):
    from github_prs import MAX_FILES, MAX_TOKENS
    from chunking import count_tokens
    from pr_document import build_document
    pr = load(os.path.join(DIR, f"{n}.json"))
    return not pr.get("not_found") and len(pr["files"]) <= MAX_FILES \
        and count_tokens(build_document(pr)["text"]) <= MAX_TOKENS


def cmd_pool(gl, n_tasks, n_dist):
    if not os.environ.get("GITLAB_TOKEN"):
        raise SystemExit("GITLAB_TOKEN is not set: merge request discussions need a token (read_api)")
    idx = load(os.path.join(DIR, "_index.json"))
    tasks, seen = [], set()
    skipped = {"issue not public": 0, "issue after MR": 0, "issue too short": 0,
               "same issue as an earlier task": 0, "MR too big": 0}
    for m in order([m for m in idx if CLOSING.search(m["description"])]):
        if len(tasks) >= n_tasks:
            break
        iss = int(CLOSING.search(m["description"]).group(1))
        if iss in seen:
            skipped["same issue as an earlier task"] += 1
            continue
        d, _ = gl.get(f"{API}/issues/{iss}", denied_ok=True)
        if d is None:
            skipped["issue not public"] += 1
            continue
        if d["created_at"] >= m["created_at"]:
            skipped["issue after MR"] += 1
            continue
        text = f"{d['title']}\n\n{d.get('description') or ''}".strip()
        if len(text.split()) < MIN_ISSUE_WORDS:
            skipped["issue too short"] += 1
            continue
        download(gl, [m["iid"]])
        if not usable(m["iid"]):
            skipped["MR too big"] += 1
            continue
        seen.add(iss)
        tasks.append({"pr_number": m["iid"], "issue": iss, "problem_statement": text,
                      "short_query": d["title"], "created_at": d["created_at"]})
    print(f"{len(tasks)} tasks; skipped {skipped}; {gl.n} requests", flush=True)
    # same-ticket filter: an MR naming a task's issue is left out as a distractor
    fix = {t["pr_number"] for t in tasks}
    chosen, same, big = [], [], []
    for m in order([m for m in idx if m["iid"] not in fix]):
        if len(chosen) >= n_dist:
            break
        hit = {int(x) for x in MENTION.findall(m["title"] + "\n" + m["description"])} & seen
        if hit:
            same.append({"number": m["iid"], "issues": sorted(hit)})
            continue
        download(gl, [m["iid"]])
        if not usable(m["iid"]):
            big.append(m["iid"])
            continue
        chosen.append(m["iid"])
        if len(chosen) % 25 == 0:
            print(f"  {len(chosen)}/{n_dist} distractors, {gl.n} requests", flush=True)
    numbers = sorted(fix | set(chosen))
    name = f"A{n_dist}"
    save(os.path.join(DIR, f"_pool_{name}.json"),
         {"pool": "A", "n_distractors": n_dist, "same_ticket": same, "excluded": big, "numbers": numbers})
    save(os.path.join("exp1_gitlab", f"tasks_{name}.json"), {"skipped": skipped, "tasks": tasks})
    print(f"Pool {name}: {len(numbers)} MRs ({len(tasks)} tasks + {len(chosen)} distractors); "
          f"same-ticket out {len(same)}, too big {len(big)}; {gl.n} requests")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["index", "pool"])
    ap.add_argument("--tasks", type=int, default=30)
    ap.add_argument("--distractors", type=int, default=270)
    a = ap.parse_args()
    gl = GitLab()
    cmd_index(gl) if a.command == "index" else cmd_pool(gl, a.tasks, a.distractors)
