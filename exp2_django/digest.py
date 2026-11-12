"""Print a readable digest of PRs (everything except the diffs) for writing questions.

    python digest.py 12345 23456 ...      # or: python digest.py --shortlist START END
"""
import json
import sys

from common import doc

MAX_PART = 1800


def digest(n):
    d = doc(n)
    out = [f"=================== PR {n}"]
    files = sorted({p["file_path"] for p in d["parts"] if p["type"] in ("hunk", "file_nodiff")})
    for p in d["parts"]:
        if p["type"] in ("hunk", "file_nodiff"):
            continue
        t = d["text"][p["start"]:p["end"]]
        out.append(f"--- [{p['type']}] {p['start']}-{p['end']}\n" + t[:MAX_PART]
                   + (" [...]" if len(t) > MAX_PART else ""))
    out.append("--- files: " + ", ".join(files))
    return "\n".join(out)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--shortlist":
        nums = [f["n"] for f in json.load(open("shortlist.json"))["shortlist"]][int(a[1]):int(a[2])]
    else:
        nums = [int(x) for x in a]
    sys.stdout.reconfigure(encoding="utf-8")
    print("\n\n".join(digest(n) for n in nums))
