"""Marks automated notes as bots in the cached MRs, offline. GitLab's API has no user type, and
Danger posts under service accounts and the deleted-user placeholder (ghost1), so these are found
by account pattern or by Danger's own text. Bodies are never edited. Decided from reading digests,
before any Exp 2 generation; Exp 1 was rerun after it."""
import glob, json, re
ACCT = re.compile(r"^service_account_|^duo-|^contributors\.gitlab\.com$", re.I)
TEXT = re.compile(r"data-danger-table|## Reviewer roulette|Reviewer roulette|Posted via \[contributors\.gitlab\.com")
n = 0
for p in glob.glob("prs/gitlab-org_gitlab-runner/[0-9]*.json"):
    d = json.load(open(p, encoding="utf-8"))
    if d.get("not_found"):
        continue
    for c in d["review_comments"] + d["issue_comments"]:
        if c["user"]["type"] != "Bot" and (ACCT.search(c["user"]["login"]) or TEXT.search(c.get("body") or "")):
            c["user"]["type"] = "Bot"; n += 1
    json.dump(d, open(p, "w", encoding="utf-8"))
print("newly marked", n)
