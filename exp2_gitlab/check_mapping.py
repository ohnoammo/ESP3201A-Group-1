"""One-MR check of the adapter mapping: GitLab fields -> github_prs JSON -> Exp 1 document."""
import sys

import gitlab_mrs as g
from pr_document import build_document

gl = g.GitLab()
n = int(sys.argv[1])
d = g.fetch_mr(gl, n)
print({k: (len(v) if isinstance(v, list) else v) for k, v in d.items() if k != "body"})
x = build_document(d)
print(x["text"][:700])
print([p["type"] for p in x["parts"]])
print("thread lines:", [p.get("line") for p in x["parts"] if p["type"] == "review_thread"])
print("hunk ranges:", [p.get("new_lines") for p in x["parts"] if p["type"] == "hunk"][:8])
