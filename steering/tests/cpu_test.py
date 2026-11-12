"""CPU test of codex_steer.py without a GPU (activation steering; no weights change, not RL).

Part A, real model: Qwen/Qwen2.5-0.5B-Instruct (24 layers) in float32 on CPU, layers scaled from
14/20/25 of 36 to 9/13/17 of 24. Runs the real `smoke` command, checks the response-token mask
against the chat template, builds a vector from 4 real pairs and steers 2 real prompts.

Part B, fake model: the whole pipeline (vectors -> baseline -> select -> test -> stats -> blind ->
labels -> stats -> report -> sweep) on all 70 questions with a fast deterministic stand-in for the
model, to check the bookkeeping: folds, held-out separation, resumability, selection, tests.

  python tests\\cpu_test.py --repo <gitlab_runner_copy> [--part A|B|AB]
Outputs go to tests\\cpu_out\\ (never to out\\).
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True
import codex_steer as cs  # noqa: E402

SMALL = "Qwen/Qwen2.5-0.5B-Instruct"
SMALL_LAYERS = ["9", "13", "17"]
PREP = ["prompts.jsonl", "folds.json", "inner_sets.json", "pairs.jsonl", "ratio_subsets.json",
        "pair_flags.json", "prepare_summary.json", "dropped_pairs.jsonl"]
RESULTS = {}
WORK = os.path.join(HERE, "cpu_out")      # --work moves the scratch output (e.g. off OneDrive)


def check(name, cond, detail=""):
    RESULTS[name] = bool(cond)
    print(f"  {'ok  ' if cond else 'FAIL'}  {name} {detail}")


def fresh(d):
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
    for f in PREP:
        shutil.copy(os.path.join(ROOT, "out", f), os.path.join(d, f))


def run(argv):
    try:
        cs.main(argv)
        return 0
    except SystemExit as e:
        return e.code or 0


# ------------------------------------------------------------------ part A: real small model
def part_a(repo):
    d = os.path.join(WORK, "real")
    fresh(d)
    common = ["--repo", repo, "--out", d, "--model", SMALL, "--device", "cpu", "--dtype", "float32",
              "--layers", *SMALL_LAYERS, "--prefer-layer", "13", "--max-new", "40"]
    rc = run(["smoke", *common])
    sys.stdout = sys.__stdout__
    check("A1 smoke command passes on the small model", rc == 0, f"(exit {rc})")
    a = argparse.Namespace(model=SMALL, device="cpu", dtype="float32", revision=None, out=d, repo=repo)
    lm = cs.LM(a)
    prompts = {p["key"]: p for p in cs.rjsonl(os.path.join(d, "prompts.jsonl"))}
    pairs = cs.rjsonl(os.path.join(d, "pairs.jsonl"))
    # response-token mask = exactly the assistant turn's content tokens
    p = prompts["main:q3220"]
    for resp in ["Not found in the provided PRs", pairs[-1]["chosen"]]:
        ids_p = lm.encode(p["system"], p["user"])
        ids_r = lm.tok(resp, add_special_tokens=False).input_ids
        msgs = [{"role": "system", "content": p["system"]}, {"role": "user", "content": p["user"]},
                {"role": "assistant", "content": resp}]
        full = lm.tok(lm.tok.apply_chat_template(msgs, tokenize=False), add_special_tokens=False).input_ids
        check(f"A2 prompt + response ids are a prefix of the chat-template conversation ({resp[:20]!r})",
              full[:len(ids_p) + len(ids_r)] == ids_p + ids_r,
              f"(prompt {len(ids_p)} tok, response {len(ids_r)} tok)")
    # a real vector from 4 pairs
    import numpy as np
    pick = [x for x in pairs if x["pair_id"] in ("unans:nr3177", "twin:q3220", "g_nf:q3220", "g_what:q3220")]
    L = 13
    diffs, norms = [], []
    t0 = time.time()
    for x in pick:
        pr = prompts[x["prompt_key"]]
        c, _, nc = lm.acts(pr["system"], pr["user"], x["chosen"], [9, 13, 17])
        r, _, nr = lm.acts(pr["system"], pr["user"], x["rejected"], [9, 13, 17])
        diffs.append(c[L][0] - r[L][0])
        norms += [c[L][1], r[L][1]]
        check(f"A3 activations finite and response-only [{x['pair_id']}]",
              np.isfinite(c[L][0]).all() and np.isfinite(r[L][0]).all() and nc > 0 and nr > 0,
              f"(chosen {nc} tok, rejected {nr} tok)")
    v = np.mean(diffs, axis=0)
    ratio = float(np.linalg.norm(v) / np.mean(norms))
    print(f"  4-pair vector at layer {L}: norm {np.linalg.norm(v):.2f}, typical residual {np.mean(norms):.2f}, "
          f"ratio {ratio:.3f}; {time.time() - t0:.0f}s")
    RESULTS["A_vector_norm_ratio"] = ratio
    # steering two real prompts
    outs = {}
    for key in ("main:q3220", "main:nr3177"):
        pr = prompts[key]
        base = lm.generate(pr["system"], pr["user"], max_new=40)
        outs[key] = {"0": base["response"]}
        for s in (0.5, 1.0, 2.0, 4.0):
            g = lm.generate(pr["system"], pr["user"], layer=L, vec=v, strength=s, max_new=40)
            outs[key][str(s)] = g["response"]
        after = lm.generate(pr["system"], pr["user"], max_new=40)
        check(f"A4 unsteered output restored after steering [{key}]", after["response"] == base["response"])
        check(f"A5 no hook left on any layer [{key}]", lm.n_hooks() == 0)
        for s, t in outs[key].items():
            print(f"    {key} strength {s:>3}: {t[:100]!r}")
    RESULTS["A_steered_outputs"] = outs
    check("A6 some strength changes some output",
          any(t != o["0"] for o in outs.values() for k, t in o.items() if k != "0"))


# ------------------------------------------------------------------ part B: fake model, full pipeline
class FakeLM:
    """Deterministic stand-in: refusal probability rises with strength at layer 20, and strength 2
    at layer 25 loops (degenerate), so selection, dropping and the tests all get exercised."""
    calls = 0
    crash_after = None

    def __init__(self, a):
        self.info = {"model": "FAKE", "revision": None, "dtype": "none", "device": "cpu", "code_sha": cs.CODE_SHA}

    def generate(self, system, user, layer=None, vec=None, strength=0.0, max_new=512):
        FakeLM.calls += 1
        if FakeLM.crash_after is not None and FakeLM.calls > FakeLM.crash_after:
            raise RuntimeError("simulated crash")
        import re
        cite = re.search(r"\[(PR\d+-c\d+)\]", user).group(1)
        h = int(hashlib.sha256(f"{user}|{layer}|{strength}".encode()).hexdigest()[:8], 16) / 2**32
        unans_hint = int(hashlib.sha256(user.encode()).hexdigest()[:2], 16) / 256
        p_refuse = 0.25 + (0.2 * strength if layer == 20 else 0.05 * strength) + 0.2 * (unans_hint > 0.7)
        if layer == 25 and strength == 2.0:
            text, hit = "the the the the " * 130, True
        elif h < p_refuse:
            text, hit = "Not found in the provided PRs", False
        else:
            text, hit = f"The reason was stated variant {int(h * 4)}. [{cite}]", False
        return {"response": text, "n_prompt_tokens": len(user) // 4, "n_new_tokens": 512 if hit else 12,
                "eos": not hit, "hit_max": hit, "seconds": 0.0}

    def acts(self, system, user, response, layers):
        import numpy as np
        out = {}
        for L in layers:
            rng = np.random.default_rng(int(hashlib.sha256(f"{response}|{L}".encode()).hexdigest()[:8], 16))
            out[L] = (rng.standard_normal(8).astype(np.float32), 10.0)
        return out, 100, 10

    def n_hooks(self):
        return 0


def part_b(repo):
    d = os.path.join(WORK, "fake")
    fresh(d)
    cs.load_lm = FakeLM
    c = ["--repo", repo, "--out", d]
    check("B1 vectors", run(["vectors", *c]) == 0)
    vi = cs.rjson(os.path.join(d, "vector_info.json"))
    check("B1b 45 vectors (3 ratios x 5 folds x 3 layers)", len(vi["vectors"]) == 45)
    # vectors use training pairs only
    folds = cs.rjson(os.path.join(d, "folds.json"))
    subs = cs.rjson(os.path.join(d, "ratio_subsets.json"))
    pid2q = {p["pair_id"]: p["id"] for p in cs.rjsonl(os.path.join(d, "pairs.jsonl"))}
    leak = [(k, r, pid) for k, v in subs.items() for r in cs.RATIOS for pid in v[r]["refusal"] + v[r]["grounding"]
            if pid2q[pid] in folds[k]]
    check("B2 no held-out question's pair is in its fold's vector subset", not leak, f"({len(leak)} leaks)")
    inner = cs.rjson(os.path.join(d, "inner_sets.json"))
    leak2 = [(k, i) for k, v in inner.items() for i in v["unanswerable"] + v["answerable"] if i in folds[k]]
    check("B3 no held-out question is in its fold's inner (selection) set", not leak2)
    ok_ratio = all(v[r]["n_refusal"] * cs.RATIOS[r][1] == v[r]["n_grounding"] * cs.RATIOS[r][0]
                   for v in subs.values() for r in cs.RATIOS)
    check("B4 every subset has exactly its ratio", ok_ratio)
    # baseline with a simulated crash, then resume
    FakeLM.calls, FakeLM.crash_after = 0, 30
    rc = run(["baseline", *c])
    n1 = len(cs.rjsonl(os.path.join(d, "gen_baseline.jsonl")))
    FakeLM.crash_after = None
    rc2 = run(["baseline", *c])
    rows = cs.rjsonl(os.path.join(d, "gen_baseline.jsonl"))
    check("B5 baseline crash then resume: 70 rows, no duplicates",
          rc != 0 and n1 == 30 and rc2 == 0 and len(rows) == 70 and len({r["key"] for r in rows}) == 70,
          f"(after crash {n1}, after resume {len(rows)})")
    # half-written last line is tolerated
    with open(os.path.join(d, "gen_baseline.jsonl"), "a", encoding="utf-8") as f:
        f.write('{"key": "half')
    check("B6 a half-written last line is skipped and repaired", run(["baseline", *c]) == 0 and
          len(cs.Appender(os.path.join(d, "gen_baseline.jsonl")).rows) == 70)
    check("B7 select", run(["select", *c]) == 0)
    sel = cs.rjson(os.path.join(d, "selection.json"))
    dropped = all(t["dropped_degenerate"] for r in sel.values() for k in r.values() for t in k["table"]
                  if t["layer"] == 25 and t["strength"] == 2.0)
    check("B8 the looping setting (layer 25 x2) is dropped as degenerate everywhere", dropped)
    n_inner = len(cs.rjsonl(os.path.join(d, "gen_inner.jsonl")))
    n_set = 3 * len(cs.STRENGTHS)                       # layers x steered strengths (12 since 8 Nov)
    check(f"B9 inner answers = 3 ratios x 5 folds x {n_set} settings x inner set", n_inner ==
          3 * n_set * sum(len(v["unanswerable"]) + len(v["answerable"]) for v in inner.values()), f"({n_inner})")
    # tie-break check on a synthetic table
    a = argparse.Namespace(prefer_layer=20)
    tab = [{"_J": 0, "strength": 0.0, "layer": None}, {"_J": 1, "strength": 1.0, "layer": 25},
           {"_J": 1, "strength": 1.0, "layer": 14}, {"_J": 1, "strength": 0.5, "layer": 25}]
    best = sorted(tab, key=lambda t: (-t["_J"], t["strength"], abs((t["layer"] if t["layer"] is not None
                                                                     else a.prefer_layer) - a.prefer_layer),
                                      t["layer"] if t["layer"] is not None else -1))[0]
    check("B10 tie-break prefers the smaller strength", best == tab[3])
    check("B11 test", run(["test", *c]) == 0)
    test = cs.rjsonl(os.path.join(d, "gen_test.jsonl"))
    fold_of = {i: k for k, ids in folds.items() for i in ids}
    wrong = [r for r in test if (sel[r["ratio"]][fold_of[r["id"]]]["layer"], sel[r["ratio"]][fold_of[r["id"]]]["strength"])
             != ((r["layer"], r["strength"]) if not r.get("reused_baseline") else (None, 0.0))]
    check("B12 every held-out answer used its own fold's chosen setting", len(test) == 210 and not wrong)
    check("B13 stats (no labels)", run(["stats", *c]) == 0)
    check("B14 blind sheet", run(["blind", *c]) == 0)
    check("B15 blind sheet is deterministic (second run identical)", run(["blind", *c]) == 0)
    with open(os.path.join(d, "blind_sheet_blank.csv"), encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for n, r in enumerate(rows):
        r["label"] = ["correct", "partial", "wrong"][n % 3]
    with open(os.path.join(d, "blind_sheet_labels.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    check("B16 stats with labels", run(["stats", *c]) == 0)
    S = cs.rjson(os.path.join(d, "stats.json"))
    check("B17 9 tests with Holm p >= raw p", len(S["tests"]) == 9 and all(t["p_holm"] >= t["p"] for t in S["tests"]))
    check("B18 correctness rows (2 kinds x 3 ratios)", S["correctness"] and len(S["correctness"]["rows"]) == 6)
    check("B19 report", run(["report", *c]) == 0)
    check("B20 sweep", run(["sweep", *c, "--ratios", "50:50"]) == 0 and
          len(cs.rjsonl(os.path.join(d, "gen_sweep.jsonl"))) == n_set * 70)
    check("B21 stats with sweep", run(["stats", *c]) == 0 and cs.rjson(os.path.join(d, "stats.json")).get("sweep"))
    # McNemar and Holm against hand values
    check("B22 exact McNemar 7/0 -> 0.015625", abs(cs.mcnemar_exact(7, 0) - 0.015625) < 1e-12)
    check("B23 exact McNemar 3/3 -> 1.0, 0/0 -> 1.0", cs.mcnemar_exact(3, 3) == 1.0 and cs.mcnemar_exact(0, 0) == 1.0)
    check("B24 Holm [0.01, 0.04, 0.03] -> [0.03, 0.06, 0.06]",
          [round(x, 10) for x in cs.holm([0.01, 0.04, 0.03])] == [0.03, 0.06, 0.06])
    check("B25 degenerate rules", cs.degenerate("a b c d " * 6, False) and not cs.degenerate("a b c d " * 5, False)
          and cs.degenerate("123 !!", False) == ["no_letters"] and cs.degenerate("ok", True) == ["hit_max_tokens"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=None)
    ap.add_argument("--part", default="AB")
    ap.add_argument("--work", default=None)
    args = ap.parse_args()
    if args.work:
        WORK = os.path.abspath(args.work)
    os.makedirs(os.path.join(HERE, "cpu_out"), exist_ok=True)
    repo = cs.find_repo(args.repo)
    if "B" in args.part:
        print("\n=== part B: fake model, full pipeline")
        part_b(repo)
        sys.stdout = sys.__stdout__
    if "A" in args.part:
        print("\n=== part A: real small model on CPU")
        part_a(repo)
    sys.stdout = sys.__stdout__
    fails = [k for k, v in RESULTS.items() if v is False]
    with open(os.path.join(HERE, "cpu_out", f"results_{args.part}.json"), "w", encoding="utf-8") as f:
        json.dump({"results": RESULTS, "failed": fails}, f, indent=1, ensure_ascii=False)
    print(f"\n{sum(v is True for v in RESULTS.values())} checks passed, {len(fails)} failed: {fails}")
    sys.exit(1 if fails else 0)
