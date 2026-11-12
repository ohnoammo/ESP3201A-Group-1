"""Copy a transfer-check repo's data into this folder, so the app can answer on it.

    python app/import_repo_data.py sympy/sympy <SymPy copy folder> <its embedding cache file>
    python app/import_repo_data.py gitlab-org/gitlab-runner <GitLab copy folder> <its cache file>

Copies the pool's PR files, chunks them exactly as the app does, and saves only the embeddings of
those chunks to emb_cache/ (the vectors aren't changed). The source folders are only read.
"""
import hashlib
import os
import shutil
import sys

import numpy as np

SOURCE, SOURCE_CACHE = os.path.abspath(sys.argv[2]), os.path.abspath(sys.argv[3])

from engine import CHUNKINGS, ENGINE, REPOS             # noqa: E402  (engine changes the folder)
from exp1_common import make_chunks                     # noqa: E402
from github_prs import cache_dir, load_pool, pool_path  # noqa: E402


def main(repo):
    r = REPOS[repo]
    os.makedirs(cache_dir(repo), exist_ok=True)
    for pool in r["pools"]:
        shutil.copy2(os.path.join(SOURCE, pool_path(repo, pool)), pool_path(repo, pool))
        numbers = load_pool(repo, pool)["numbers"]
        for n in numbers:
            shutil.copy2(os.path.join(SOURCE, cache_dir(repo), f"{n}.json"), cache_dir(repo))
        print(f"{repo} {pool}: {len(numbers)} PR files")

    with np.load(SOURCE_CACHE) as d:
        keys, emb = d["keys"], d["emb"]
    have = set(keys.tolist())
    want = set()
    for pool in r["pools"]:
        p = ENGINE._pool(repo, pool)
        docs = [p["docs"][k] for k in sorted(p["docs"], key=int)]
        for name in r["dense_chunkings"]:
            chunks, info = make_chunks(docs, CHUNKINGS[name], r["dataset"])
            hashes = {hashlib.sha1(c["text"].encode("utf-8")).hexdigest() for c in chunks}
            print(f"  {name}: {len(chunks)} chunks, set {info['chunk_set']}, "
                  f"{len(hashes & have)}/{len(hashes)} distinct texts embedded")
            if hashes - have:
                raise SystemExit(f"{name}: these documents differ from the ones embedded")
            want |= hashes
    mask = np.array([k in want for k in keys.tolist()])
    os.makedirs("emb_cache", exist_ok=True)
    path = ENGINE.dense_cache_path(repo)
    np.savez(path, keys=keys[mask], emb=emb[mask])
    print(f"  {path}: {mask.sum()} of {len(keys)} embeddings, {os.path.getsize(path) >> 20} MB")


if __name__ == "__main__":
    main(sys.argv[1])
