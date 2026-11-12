"""Download pull requests from GitHub and cache one JSON per PR (Experiment 1 data).

The token is read from the GITHUB_TOKEN environment variable (never pass it on the command
line or paste it into files). Set it in your own terminal first:
    PowerShell:  $env:GITHUB_TOKEN = "<your token>"
    bash:        export GITHUB_TOKEN=<your token>

Commands (run in this order):
    python github_prs.py index            # list every PR of the repo (number, dates, state)
    python github_prs.py fixing           # download the SWE-bench fixing PRs + report their state
    python github_prs.py size-check       # pool B (date windows) vs pool A sizes + time estimate
    python github_prs.py download --pool B --window-days 365      # or:
    python github_prs.py download --pool A --n-distractors 2000

Per PR it fetches: details, /commits, /files (diff per file), /comments (review comments),
/issues/{n}/comments (conversation). Everything is cached in prs/<owner>_<repo>/<n>.json, so
an interrupted run resumes. Rate limits: waits until the limit resets, retries on errors.

Django quirk: maintainers often land changes by committing directly, so many PRs are
"closed" without being "merged" - including fixing PRs. Pools are therefore NOT filtered on
merged state.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import time

import requests

from swebench_loader import load_swebench, to_ts

API = "https://api.github.com"
REQS_PER_PR = 5          # details, commits, files, review comments, conversation (+ pages)
HOURLY_LIMIT = 5000


# ---------- HTTP with rate-limit handling ----------
class GitHub:
    def __init__(self, token=None):
        token = token or os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("GITHUB_TOKEN is not set. In PowerShell: $env:GITHUB_TOKEN = \"<token>\"")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}",
                               "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})
        self.n_requests = 0

    def get(self, url, params=None, tries=10):
        """GET with retries: waits out rate limits; retries network errors and 5xx server
        errors with growing waits (up to 2 min, ~10 min in total) before giving up."""
        for attempt in range(tries):
            wait = min(120, 2 ** (attempt + 1))
            try:
                r = self.s.get(url, params=params, timeout=60)
            except requests.RequestException as e:
                print(f"  network error ({e.__class__.__name__}), retry {attempt + 1}/{tries} "
                      f"in {wait}s")
                time.sleep(wait)
                continue
            self.n_requests += 1
            if r.status_code in (403, 429):
                wait = None
                if r.headers.get("X-RateLimit-Remaining") == "0":        # hourly limit used up
                    wait = int(r.headers.get("X-RateLimit-Reset", time.time() + 60)) - time.time() + 5
                elif "retry-after" in r.headers:                         # secondary limit
                    wait = int(r.headers["retry-after"])
                elif "rate limit" in r.text.lower():
                    wait = 60
                if wait is not None:
                    wait = max(5, wait)
                    print(f"  rate limit reached; sleeping {wait / 60:.1f} min")
                    time.sleep(wait)
                    continue
            if r.status_code >= 500:
                print(f"  GitHub server error {r.status_code}, retry {attempt + 1}/{tries} "
                      f"in {wait}s")
                time.sleep(wait)
                continue
            if r.status_code == 404:
                return None, r
            r.raise_for_status()
            return r.json(), r
        raise RuntimeError(f"giving up on {url}")

    def paginate(self, url, params=None):
        out, params = [], dict(params or {}, per_page=100)
        while url:
            data, r = self.get(url, params)
            if data is None:
                break
            out.extend(data)
            url, params = r.links.get("next", {}).get("url"), None   # next link has params
        return out


# ---------- one PR ----------
def _user(u):
    return {"login": (u or {}).get("login"), "type": (u or {}).get("type")}


def fetch_pr(gh, repo, n):
    base = f"{API}/repos/{repo}"
    d, _ = gh.get(f"{base}/pulls/{n}")
    if d is None:
        return None
    files = gh.paginate(f"{base}/pulls/{n}/files")
    return {
        "number": n, "repo": repo,
        "title": d.get("title"), "body": d.get("body"), "state": d.get("state"),
        "merged": bool(d.get("merged_at")), "user": _user(d.get("user")),
        "created_at": d.get("created_at"), "closed_at": d.get("closed_at"),
        "merged_at": d.get("merged_at"),
        "commits": [{"sha": c["sha"], "message": c["commit"]["message"],
                     "author": (c["commit"].get("author") or {}).get("name")}
                    for c in gh.paginate(f"{base}/pulls/{n}/commits")],
        "files": [{"filename": f["filename"], "status": f.get("status"),
                   "previous_filename": f.get("previous_filename"),
                   "additions": f.get("additions"), "deletions": f.get("deletions"),
                   "patch": f.get("patch")} for f in files],
        "files_truncated": len(files) >= 3000,           # GitHub lists at most 3000 files
        "missing_patches": [f["filename"] for f in files if f.get("patch") is None],
        "review_comments": [{"id": c["id"], "in_reply_to_id": c.get("in_reply_to_id"),
                             "user": _user(c.get("user")), "body": c.get("body"),
                             "path": c.get("path"), "diff_hunk": c.get("diff_hunk"),
                             "line": c.get("line"), "original_line": c.get("original_line"),
                             "created_at": c.get("created_at")}
                            for c in gh.paginate(f"{base}/pulls/{n}/comments")],
        "issue_comments": [{"id": c["id"], "user": _user(c.get("user")), "body": c.get("body"),
                            "created_at": c.get("created_at")}
                           for c in gh.paginate(f"{base}/issues/{n}/comments")],
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def cache_dir(repo):
    return os.path.join("prs", repo.replace("/", "_"))


def pr_path(repo, n):
    return os.path.join(cache_dir(repo), f"{n}.json")


def load_pr(repo, n):
    path = pr_path(repo, n)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, path)                                # never a half-written file


def download(gh, repo, numbers):
    todo = [n for n in numbers if not os.path.exists(pr_path(repo, n))]
    print(f"{len(numbers)} PRs requested, {len(numbers) - len(todo)} cached, {len(todo)} to "
          f"download (~{len(todo) * REQS_PER_PR / HOURLY_LIMIT:.1f} h at the hourly limit)")
    missing, failed, t0 = [], [], time.time()
    for i, n in enumerate(todo, 1):
        try:
            pr = fetch_pr(gh, repo, n)
        except (RuntimeError, requests.RequestException) as e:   # skip, retry on next run
            failed.append(n)
            print(f"  PR #{n} failed ({e}); skipped, will be retried when you re-run")
            continue
        if pr is None:
            missing.append(n)
            _write_json(pr_path(repo, n), {"number": n, "repo": repo, "not_found": True})
        else:
            _write_json(pr_path(repo, n), pr)
        if i % 25 == 0 or i == len(todo):
            rate = i / max(1e-9, time.time() - t0)
            print(f"  {i}/{len(todo)} done ({gh.n_requests} requests, "
                  f"~{(len(todo) - i) / max(rate, 1e-9) / 60:.0f} min left)")
    if missing:
        print(f"  {len(missing)} PR numbers not found (deleted or issues): {missing[:10]}...")
    if failed:
        print(f"  {len(failed)} PRs failed after retries: {failed[:20]}. Re-run the same command "
              f"to fetch just these (everything else is cached).")


# ---------- index of all PRs ----------
def index_path(repo):
    return os.path.join(cache_dir(repo), "_index.json")


def build_index(gh, repo):
    """Every PR of the repo: number, created_at, state, merged_at (~1 request per 100 PRs)."""
    prs = gh.paginate(f"{API}/repos/{repo}/pulls",
                      {"state": "all", "sort": "created", "direction": "asc"})
    idx = [{"number": p["number"], "created_at": p["created_at"],
            "created_ts": to_ts(p["created_at"]), "state": p["state"],
            "merged_at": p.get("merged_at")} for p in prs]
    _write_json(index_path(repo), idx)
    print(f"Indexed {len(idx)} PRs of {repo} ({gh.n_requests} requests) -> {index_path(repo)}")
    return idx


def load_index(repo):
    if not os.path.exists(index_path(repo)):
        sys.exit("No PR index yet: run  python github_prs.py index  first")
    with open(index_path(repo), encoding="utf-8") as f:
        return json.load(f)


# ---------- pools ----------
DAY = 86400.0


def window_candidates(idx, task, window_days):
    """Pool B: PRs created within [bug date, bug date + window]. Bug date ~ fixing PR date."""
    lo, hi = task["created_ts"], task["created_ts"] + window_days * DAY
    return [p["number"] for p in idx if lo <= p["created_ts"] <= hi]


def pool_b(idx, tasks, window_days):
    union = set(t["pr_number"] for t in tasks)
    for t in tasks:
        union.update(window_candidates(idx, t, window_days))
    return sorted(union)


def distractor_order(idx, tasks, seed=42):
    """All non-fixing PRs from the tasks' period, in a fixed pseudo-random order (SHA-256)."""
    fixing = {t["pr_number"] for t in tasks}
    lo = min(t["created_ts"] for t in tasks)
    hi = max(t["created_ts"] for t in tasks)
    others = [p["number"] for p in idx
              if lo <= p["created_ts"] <= hi and p["number"] not in fixing]
    return sorted(others, key=lambda n: hashlib.sha256(f"{seed}:{n}".encode()).hexdigest())


def pool_a(idx, tasks, n_distractors, seed=42):
    """First n candidates in the fixed order, BEFORE the size filter (used for estimates)."""
    fixing = {t["pr_number"] for t in tasks}
    return sorted(fixing | set(distractor_order(idx, tasks, seed)[:n_distractors]))


# Pool size filter: very large PRs are accidental branch merges / mistakes (e.g. "Stable/3.0.x",
# 3,000 files), not code reviews. They are left out of the pool (their content is never
# changed). No fixing PR comes close (max 20 files, 9,977 tokens for django).
MAX_FILES, MAX_TOKENS = 100, 50_000


def pr_size(repo, n):
    """{'files', 'tokens', 'truncated'} of a cached PR, {'not_found': True}, or None."""
    from pr_document import build_document
    from chunking import count_tokens
    pr = load_pr(repo, n)
    if pr is None:
        return None
    if pr.get("not_found"):
        return {"not_found": True}
    return {"files": len(pr.get("files", [])), "truncated": bool(pr.get("files_truncated")),
            "tokens": count_tokens(build_document(pr)["text"])}


def too_big(size, max_files=MAX_FILES, max_tokens=MAX_TOKENS):
    return size["truncated"] or size["files"] > max_files or size["tokens"] > max_tokens


def tickets(title):
    """Django Trac ticket numbers mentioned in a PR title ('Fixed #29834 -- ...')."""
    return set(re.findall(r"#(\d{4,6})", title or ""))


def build_pool_a(gh, repo, idx, tasks, n_distractors, max_files=MAX_FILES,
                 max_tokens=MAX_TOKENS, seed=42, drop_same_ticket=True):
    """Pool A with two filters: walk the fixed candidate order, skip PRs over the size
    limits, PRs whose title mentions the same Trac ticket as a fixing PR (another attempt /
    follow-up / backport for the same bug, which would be scored as a wrong answer), and PR
    numbers that no longer exist; continue until n_distractors eligible PRs are found.
    Fixing PRs are always kept (and checked against the limits). gh=None: no downloads, just
    report how far the cached PRs get."""
    fixing = sorted({t["pr_number"] for t in tasks})
    if gh:
        download(gh, repo, fixing)
    big_fixing = [n for n in fixing if (s := pr_size(repo, n)) and not s.get("not_found")
                  and too_big(s, max_files, max_tokens)]
    fix_tickets = set()
    for n in fixing:
        fix_tickets |= tickets((load_pr(repo, n) or {}).get("title"))
    order = distractor_order(idx, tasks, seed)
    chosen, excluded, same_ticket, not_found, pos = [], [], [], [], 0
    while len(chosen) < n_distractors and pos < len(order):
        batch = order[pos:pos + (n_distractors - len(chosen))]
        need = [n for n in batch if not os.path.exists(pr_path(repo, n))]
        if need:
            if gh is None:
                print(f"  {len(need)} more candidate PRs need downloading to fill the pool")
                break
            download(gh, repo, need)
        pos += len(batch)
        for n in batch:
            s = pr_size(repo, n)
            if s is None:                          # download failed: retried on next run
                continue
            if s.get("not_found"):
                not_found.append(n)
            elif too_big(s, max_files, max_tokens):
                excluded.append({"number": n} | s)
            elif drop_same_ticket and (t := tickets(load_pr(repo, n).get("title")) & fix_tickets):
                same_ticket.append({"number": n, "tickets": sorted(t)})
            else:
                chosen.append(n)
    info = {"pool": "A", "n_distractors": n_distractors, "max_files": max_files,
            "max_tokens": max_tokens, "n_excluded": len(excluded), "excluded": excluded,
            "drop_same_ticket": drop_same_ticket, "n_same_ticket": len(same_ticket),
            "same_ticket": same_ticket,
            "n_not_found": len(not_found), "fixing_over_limits": big_fixing,
            "complete": len(chosen) >= n_distractors}
    print(f"Size filter (> {max_files} files or > {max_tokens:,} tokens): {len(excluded)} PRs "
          f"excluded; same-ticket filter: {len(same_ticket)} PRs excluded; {len(not_found)} PR "
          f"numbers not found; fixing PRs over the limits: {len(big_fixing)}; eligible "
          f"distractors {len(chosen)}/{n_distractors}")
    return sorted(set(fixing) | set(chosen)), info


# ---------- pool H: hard distractors that look like the fixing PRs ----------
LOOKALIKE_TITLE = re.compile(r"^(Fixed|Refs) #\d+")


def module_of(path):
    """'django/db/models/query.py' -> 'django/db/models'; 'django/utils/html.py' -> 'django/utils'."""
    parts = path.split("/")
    return "/".join(parts[:3]) if len(parts) > 3 else "/".join(parts[:-1])


def neighbour_of(module):
    """Parent folder: 'django/db/models' -> 'django/db'. Two-level modules ('django/utils')
    have no narrower parent than 'django' itself, so their neighbour is the module itself."""
    parent = module.rsplit("/", 1)[0]
    return module if parent == "django" else parent


def pr_modules(pr):
    """Modules of a PR's source files (under django/; tests/ and docs/ don't count)."""
    return {module_of(f["filename"]) for f in pr.get("files", [])
            if f["filename"].startswith("django/")}


def is_lookalike(pr):
    """Looks like a bug fix: merged, touches tests/, title 'Fixed #N' / 'Refs #N'."""
    return (bool(pr.get("merged"))
            and any(f["filename"].startswith("tests/") for f in pr.get("files", []))
            and bool(LOOKALIKE_TITLE.match(pr.get("title") or "")))


def fixing_module(task, pr):
    """The fixing PR's main module: most common module among SWE-bench's patch files."""
    mods = [module_of(p) for p in task["patch_files"] if p.startswith("django/")]
    if not mods:
        mods = sorted(pr_modules(pr or {}))
    return max(sorted(set(mods)), key=mods.count) if mods else None


def _assign_h(tasks, cands, quota, seed, tiers=(1, 2, 3)):
    """Deterministic assignment. cands: {number: (modules, lookalike)}. Fallback order, fixed
    in advance: tier 1 same module + look-alike; tier 2 neighbouring module + look-alike;
    tier 3 same module, any PR. Fixing PRs take turns (round robin) inside each tier."""
    used, got, tier_of = set(), {t["pr_number"]: [] for t in tasks}, {}
    order = sorted(cands, key=lambda n: hashlib.sha256(f"{seed}:{n}".encode()).hexdigest())
    rules = {1: lambda m, look, fm: look and fm in m,
             2: lambda m, look, fm: look and any(neighbour_of(x) == neighbour_of(fm) for x in m),
             3: lambda m, look, fm: fm in m}
    for tier in tiers:
        pointers = {t["pr_number"]: 0 for t in tasks}
        progress = True
        while progress:
            progress = False
            for t in tasks:
                fpr, fm = t["pr_number"], t["_module"]
                if fm is None or len(got[fpr]) >= quota[fpr]:
                    continue
                i = pointers[fpr]
                while i < len(order):
                    n = order[i]
                    i += 1
                    m, look = cands[n]
                    if n not in used and rules[tier](m, look, fm):
                        used.add(n)
                        got[fpr].append(n)
                        tier_of[n] = tier
                        progress = True
                        break
                pointers[fpr] = i
    return got, tier_of


def build_pool_h(gh, repo, idx, tasks, n_distractors, max_files=MAX_FILES,
                 max_tokens=MAX_TOKENS, seed=42, batch=200, max_downloads=6000):
    """Pool H (hard): the fixing PRs + n_distractors look-alike PRs from the SAME AREA of the
    code. Each fixing PR gets ~n/231 distractors, filled in the fallback order (see _assign_h).
    Same period, size filter and same-ticket filter as pool A. Downloads candidates in batches
    (merged PRs first) only while some fixing PR still needs distractors. gh=None: use cached
    PRs only and report the shortfall."""
    fixing = sorted({t["pr_number"] for t in tasks})
    if gh:
        download(gh, repo, fixing)
    fix_tickets = set()
    for n in fixing:
        fix_tickets |= tickets((load_pr(repo, n) or {}).get("title"))
    tasks = [t | {"_module": fixing_module(t, load_pr(repo, t["pr_number"]))} for t in tasks]
    order_t = sorted(tasks, key=lambda t: hashlib.sha256(f"{seed}:{t['pr_number']}".encode()).hexdigest())
    base, extra = divmod(n_distractors, len(order_t))
    quota = {t["pr_number"]: base + (i < extra) for i, t in enumerate(order_t)}

    merged = {p["number"]: bool(p.get("merged_at")) for p in idx}
    order = distractor_order(idx, tasks, seed)
    order.sort(key=lambda n: not merged.get(n, False))          # merged first (stable)
    cands, skipped, downloaded = {}, {"too_big": 0, "same_ticket": 0, "not_found": 0}, 0

    def classify(numbers):
        for n in numbers:
            if n in cands or not os.path.exists(pr_path(repo, n)):
                continue
            pr = load_pr(repo, n)
            if pr.get("not_found"):
                skipped["not_found"] += 1
            elif too_big(pr_size(repo, n), max_files, max_tokens):
                skipped["too_big"] += 1
            elif tickets(pr.get("title")) & fix_tickets:
                skipped["same_ticket"] += 1
            else:
                cands[n] = (pr_modules(pr), is_lookalike(pr))

    classify(order)                                             # everything already cached
    pos = 0
    while True:
        # keep downloading while tiers 1-2 (look-alike) can't fill every slot: the tier-3
        # fallback (any PR from the same module) is only used once candidates run out
        got12, _ = _assign_h(order_t, cands, quota, seed, tiers=(1, 2))
        short = sum(quota[f] - len(got12[f]) for f in quota)
        todo = []
        while pos < len(order) and len(todo) < batch:
            if not os.path.exists(pr_path(repo, order[pos])):
                todo.append(order[pos])
            pos += 1
        if short == 0 or gh is None or not todo or downloaded >= max_downloads:
            break
        print(f"  {short} slots without a look-alike yet -> downloading {len(todo)} more candidates")
        download(gh, repo, todo)
        downloaded += len(todo)
        classify(todo)

    got, tier_of = _assign_h(order_t, cands, quota, seed)         # final: all three tiers
    short = sum(quota[f] - len(got[f]) for f in quota)
    chosen = sorted(n for ns in got.values() for n in ns)
    tiers = {k: sum(1 for n in chosen if tier_of[n] == k) for k in (1, 2, 3)}
    no_module = [t["pr_number"] for t in tasks if t["_module"] is None]
    info = {"pool": "H", "n_distractors": n_distractors, "max_files": max_files,
            "max_tokens": max_tokens, "drop_same_ticket": True,
            "fallback_order": ["same module + look-alike", "neighbouring module + look-alike",
                               "same module, any PR"],
            "lookalike": "merged + touches tests/ + title 'Fixed #N' / 'Refs #N'",
            "module": "first 3 path parts of django/ source files (e.g. django/db/models)",
            "tier_counts": tiers, "n_chosen": len(chosen), "shortfall": short,
            "skipped": skipped, "fixing_without_module": no_module,
            "candidates_classified": len(cands), "new_downloads": downloaded,
            "complete": short == 0,
            "per_fixing_pr": {str(f): len(v) for f, v in got.items()}}
    print(f"Pool H: {len(chosen)}/{n_distractors} distractors -- tier 1 (same module + "
          f"look-alike) {tiers[1]}, tier 2 (neighbouring module + look-alike) {tiers[2]}, "
          f"tier 3 (same module, any) {tiers[3]}; empty slots {short}; skipped {skipped}; "
          f"fixing PRs with no django/ module: {len(no_module)}")
    return sorted(set(fixing) | set(chosen)), info


def pool_path(repo, name):
    return os.path.join(cache_dir(repo), f"_pool_{name}.json")


def save_pool(repo, name, numbers, info):
    _write_json(pool_path(repo, name), info | {"numbers": numbers})
    print(f"Pool '{name}': {len(numbers)} PRs -> {pool_path(repo, name)}")


def load_pool(repo, name):
    with open(pool_path(repo, name), encoding="utf-8") as f:
        return json.load(f)


def pool_name(pool, window_days=None, n_distractors=None):
    return f"B{window_days}d" if pool == "B" else f"{pool}{n_distractors}"


# ---------- commands ----------
def cmd_fixing(gh, repo):
    tasks = load_swebench(repo)
    download(gh, repo, sorted({t["pr_number"] for t in tasks}))
    states = {"merged": 0, "closed_not_merged": 0, "open": 0, "not_found": 0}
    for t in tasks:
        pr = load_pr(repo, t["pr_number"])
        if pr is None or pr.get("not_found"):
            states["not_found"] += 1
        elif pr["merged"]:
            states["merged"] += 1
        elif pr["state"] == "closed":
            states["closed_not_merged"] += 1
        else:
            states["open"] += 1
    print(f"Fixing PRs of {len(tasks)} tasks: {states}")


def cmd_size_check(repo, windows=(365, 182, 91), distractors=(2000, 3000)):
    import statistics as st
    idx, tasks = load_index(repo), load_swebench(repo)
    lo = min(t["created_at"] for t in tasks)
    hi = max(t["created_at"] for t in tasks)
    print(f"{len(tasks)} bugs, dates {lo} .. {hi}; repo has {len(idx)} PRs in total")
    for w in windows:
        per = [len(window_candidates(idx, t, w)) for t in tasks]
        union = pool_b(idx, tasks, w)
        todo = sum(not os.path.exists(pr_path(repo, n)) for n in union)
        print(f"  Pool B, window {w:>3} days: candidates per bug median {st.median(per):.0f} "
              f"(min {min(per)}, max {max(per)}); union {len(union)} PRs, {todo} not cached "
              f"-> ~{todo * REQS_PER_PR / HOURLY_LIMIT:.1f} h")
    for n in distractors:
        pool = pool_a(idx, tasks, n)
        todo = sum(not os.path.exists(pr_path(repo, x)) for x in pool)
        print(f"  Pool A, {n} distractors: {len(pool)} PRs, {todo} not cached "
              f"-> ~{todo * REQS_PER_PR / HOURLY_LIMIT:.1f} h")


def cmd_download(gh, repo, pool, window_days, n_distractors, limit=None,
                 max_files=MAX_FILES, max_tokens=MAX_TOKENS):
    idx, tasks = load_index(repo), load_swebench(repo)
    name = pool_name(pool, window_days, n_distractors)
    if pool in ("A", "H"):                # downloads as it goes; filters applied
        build = build_pool_a if pool == "A" else build_pool_h
        numbers, info = build(gh, repo, idx, tasks, n_distractors, max_files, max_tokens)
        save_pool(repo, name, numbers, info | {"repo": repo})
        if gh is not None and not info["complete"]:
            print("Pool not complete (some downloads failed): re-run the same command.")
        return
    numbers = pool_b(idx, tasks, window_days)          # pool B: no size filter yet
    save_pool(repo, name, numbers, {"pool": "B", "window_days": window_days, "repo": repo})
    fixing = {t["pr_number"] for t in tasks}
    order = sorted(numbers, key=lambda n: (n not in fixing, n))   # fixing PRs first
    download(gh, repo, order[:limit] if limit else order)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["index", "fixing", "size-check", "pool-check",
                                        "download"])
    ap.add_argument("--repo", default="django/django")
    ap.add_argument("--pool", choices=["A", "B", "H"], default="B",
                    help="A = random distractors, H = hard (look-alike, same module), B = windows")
    ap.add_argument("--window-days", type=int, default=365)
    ap.add_argument("--n-distractors", type=int, default=2000)
    ap.add_argument("--max-files", type=int, default=MAX_FILES,
                    help="pool A: leave out PRs changing more files than this")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS,
                    help="pool A: leave out PRs whose document is longer than this")
    ap.add_argument("--limit", type=int, default=None, help="download at most this many PRs")
    a = ap.parse_args()
    if a.command == "size-check":
        cmd_size_check(a.repo)
    elif a.command == "pool-check":                     # cached PRs only, no token needed
        build = build_pool_h if a.pool == "H" else build_pool_a
        build(None, a.repo, load_index(a.repo), load_swebench(a.repo), a.n_distractors,
              a.max_files, a.max_tokens)
    elif a.command == "download" and a.pool in ("A", "H"):
        cmd_download(GitHub(), a.repo, a.pool, a.window_days, a.n_distractors, a.limit,
                     a.max_files, a.max_tokens)
    else:
        gh = GitHub()
        if a.command == "index":
            build_index(gh, a.repo)
        elif a.command == "fixing":
            cmd_fixing(gh, a.repo)
        else:
            cmd_download(gh, a.repo, a.pool, a.window_days, a.n_distractors, a.limit)
