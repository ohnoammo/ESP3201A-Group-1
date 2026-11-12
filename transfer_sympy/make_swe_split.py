"""Split the SWE-bench tasks of one repo into dev (tuning) and test (final run, once).

    python make_swe_split.py --repo django/django            # dev 50 / test 181
    python make_swe_split.py --from-ids swe_split_ids.json   # check a shared split

Same approach as the old QASPER split: no random number generator. Each task's position is
SHA-256("<seed>:<instance_id>"); tasks are sorted by it and the first n_dev go to dev. Same
result on every OS / Python version / input order. Prints a fingerprint: everyone in the
group should see the same value. Saved to swe_split_ids.json.
"""
import argparse
import hashlib
import json

from swebench_loader import load_swebench


def hash_key(seed, iid):
    return hashlib.sha256(f"{seed}:{iid}".encode("utf-8")).hexdigest()


def fingerprint(split):
    text = "|".join(sorted(split["dev"])) + "||" + "|".join(sorted(split["test"]))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def make_split(ids, n_dev, seed):
    order = sorted(ids, key=lambda i: (hash_key(seed, i), i))
    return {"dev": sorted(order[:n_dev]), "test": sorted(order[n_dev:])}


def load_split(path="swe_split_ids.json"):
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    if s.get("fingerprint") and s["fingerprint"] != fingerprint(s):
        raise ValueError(f"{path} looks edited: fingerprint does not match its ids")
    return s


def main(repo, n_dev, seed, out, from_ids=None):
    ids = [t["instance_id"] for t in load_swebench(repo)]
    if from_ids:
        split = load_split(from_ids)
        missing = (set(split["dev"]) | set(split["test"])) - set(ids)
        if missing:
            raise ValueError(f"{len(missing)} ids in {from_ids} are not in {repo}")
        print(f"Loaded split from {from_ids}")
    else:
        split = make_split(ids, n_dev, seed)
        assert not set(split["dev"]) & set(split["test"])
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"repo": repo, "seed": seed, "n_dev": n_dev,
                       "method": "sha256(seed:instance_id)", "fingerprint": fingerprint(split)}
                      | split, f, indent=1)
        print(f"Saved {out}")
    print(f"{repo}: dev {len(split['dev'])}, test {len(split['test'])}")
    print(f"Split fingerprint: {fingerprint(split)}   <- everyone should see the same value")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="django/django")
    ap.add_argument("--n-dev", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="swe_split_ids.json")
    ap.add_argument("--from-ids", default=None)
    a = ap.parse_args()
    main(a.repo, a.n_dev, a.seed, a.out, a.from_ids)
