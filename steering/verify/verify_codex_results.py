r"""verify_codex_results.py: an independent check of the Codex-build steering results (Claude, 8 Nov 2026).

This is activation steering, not RL or fine-tuning. The script does not import codex_steer.py. It
recomputes everything it can from the raw outputs, using its own code, and stops at the first
disagreement with what the Codex build reported.

Usage (CPU, on Clifton's PC, after unzipping James's results into Latest\CODEX_steering\out):
  python verify_codex_results.py --out "...\Latest\CODEX_steering\out" --repo "...\gitlab_runner_copy"

Checks:
 1. Folds, inner sets and ratio subsets: each covers what it should, nothing held out leaks into a
    fold's vector or inner set, and the ratios are exact.
 2. Every stored response is re-scored from its raw text with exp2_gitlab_scale.auto(); the result
    must match the stored abstained / answered / overlap_cited flags.
 3. The degenerate rule is recomputed with an independent implementation.
 4. The selection is recomputed from gen_inner + gen_baseline (J, the 10% degenerate drop,
    tie-breaks) and must equal selection.json.
 5. Every test row used its own fold's chosen (layer, strength); a strength-0 row equals the baseline.
 6. The arm counts, exact McNemar p and Holm p are recomputed and must equal stats.json.
 7. The blind sheet holds exactly the distinct answered answerable answers (the key is NOT read).
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from fractions import Fraction
from math import comb

RATIOS = {"40:60": (2, 3), "50:50": (1, 1), "60:40": (3, 2)}
FAIL = []


def rj(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        FAIL.append(name)


def degenerate(text, hit_max):
    if not any(ch.isalpha() for ch in text):
        return True
    if hit_max:
        return True
    w = re.findall(r"\w+", text.lower())
    seen = defaultdict(int)
    for i in range(len(w) - 3):
        seen[tuple(w[i:i + 4])] += 1
    return bool(seen) and max(seen.values()) >= 6


def mcnemar(b, c):
    n = b + c
    if n == 0:
        return 1.0
    return min(1.0, 2 * sum(comb(n, i) for i in range(min(b, c) + 1)) / 2 ** n)


def holm(ps):
    idx = sorted(range(len(ps)), key=lambda i: ps[i])
    out, prev = [0.0] * len(ps), 0.0
    for r, i in enumerate(idx):
        prev = max(prev, min(1.0, (len(ps) - r) * ps[i]))
        out[i] = prev
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    O = lambda *n: os.path.join(a.out, *n)
    sys.path.insert(0, a.repo)
    os.chdir(a.repo)
    sys.dont_write_bytecode = True
    import exp2_gitlab_scale as E

    qd = {q["id"]: q for q in E.read_jsonl(E.QUESTIONS)}
    ans = [i for i, q in qd.items() if q["type"] == "answerable"]
    un = [i for i, q in qd.items() if q["type"] != "answerable"]
    P = {p["key"]: p for p in rj(O("prompts.jsonl"))}
    pairs = {p["pair_id"]: p for p in rj(O("pairs.jsonl"))}
    folds = json.load(open(O("folds.json")))
    fold_of = {i: k for k, v in folds.items() for i in v}
    inner = json.load(open(O("inner_sets.json")))
    subs = json.load(open(O("ratio_subsets.json")))

    print("1. folds, inner sets, ratio subsets")
    dropped = {p["pair_id"] for p in rj(O("dropped_pairs.jsonl"))} if os.path.exists(O("dropped_pairs.jsonl")) else set()
    used = {i for v in subs.values() for r in RATIOS for i in v[r]["refusal"] + v[r]["grounding"]}
    check(f"none of the {len(dropped)} human-dropped pairs is in pairs.jsonl or any vector subset",
          not (dropped & set(pairs)) and not (dropped & used))
    check("folds cover the 70 once", sorted(fold_of) == sorted(qd) and sum(map(len, folds.values())) == 70)
    for k in folds:
        bad_inner = [i for i in inner[k]["unanswerable"] + inner[k]["answerable"] if fold_of[i] == k]
        tr_un = sorted(i for i in un if fold_of[i] != k)
        check(f"fold {k}: inner set has no held-out MR and all training unanswerables",
              not bad_inner and sorted(inner[k]["unanswerable"]) == tr_un and len(inner[k]["answerable"]) == 14)
        for r, (x, y) in RATIOS.items():
            s = subs[k][r]
            ids = s["refusal"] + s["grounding"]
            leak = [i for i in ids if fold_of[pairs[i]["id"]] == k]
            fam = all(pairs[i]["family"] == "refusal" for i in s["refusal"]) and \
                all(pairs[i]["family"] == "grounding" for i in s["grounding"])
            exact = len(s["refusal"]) * y == len(s["grounding"]) * x
            tr = [p for p in pairs.values() if fold_of[p["id"]] != k]
            nr = sum(p["family"] == "refusal" for p in tr)
            ng = len(tr) - nr
            m = min(nr // x, ng // y)
            check(f"fold {k} {r}: no leak, right families, exact and largest ratio",
                  not leak and fam and exact and len(s["refusal"]) == m * x and len(set(ids)) == len(ids))

    base = {r["id"]: r for r in rj(O("gen_baseline.jsonl"))}
    test = defaultdict(dict)
    for r in rj(O("gen_test.jsonl")):
        test[r["ratio"]][r["id"]] = r
    inner_rows = {r["key"]: r for r in rj(O("gen_inner.jsonl"))} if os.path.exists(O("gen_inner.jsonl")) else {}

    print("2-3. re-scoring every response from its raw text")
    mism, dmism = [], []
    for name, rows in [("baseline", base.values()), ("test", [r for d in test.values() for r in d.values()]),
                       ("inner", inner_rows.values())]:
        for r in rows:
            q = qd[r["id"]]
            x = E.auto({"response": r["response"], "context_short_ids": P[r["prompt_key"]]["context_short_ids"]},
                       q, "fixed_s512_o77")
            answered = (not x["abstained"]) and (not x["empty_answer"])
            if (x["abstained"], answered, x["overlap_cited"]) != (r["abstained"], r["answered"], r["overlap_cited"]):
                mism.append(r["key"])
            if degenerate(r["response"], r["hit_max"]) != bool(r["degenerate"]):
                dmism.append(r["key"])
    check("stored abstained / answered / overlap_cited equal a fresh re-score", not mism, f"{len(mism)} differ: {mism[:5]}")
    check("degenerate flags equal an independent implementation", not dmism, f"{len(dmism)} differ: {dmism[:5]}")

    print("4. selection recomputed")
    sel = json.load(open(O("selection.json")))
    strengths = sorted({r["strength"] for r in inner_rows.values()})
    layers = sorted({r["layer"] for r in inner_rows.values()})
    check("grid seen in gen_inner", bool(strengths) and bool(layers), f"layers {layers}, strengths {strengths}")
    for r in RATIOS:
        for k in folds:
            U, A = inner[k]["unanswerable"], inner[k]["answerable"]
            best = None
            for L, s in [(None, 0.0)] + [(L, s) for L in layers for s in strengths]:
                rows = [base[i] if s == 0 else inner_rows.get(f"inner|{r}|f{k}|L{L}|s{s}|{i}") for i in U + A]
                if any(x is None for x in rows):
                    FAIL.append(f"missing inner rows {r} f{k} L{L} s{s}")
                    continue
                J = Fraction(sum(x["abstained"] for x in rows[:len(U)]), len(U)) + \
                    Fraction(sum(x["answered"] for x in rows[len(U):]), len(A)) - 1
                deg = Fraction(sum(degenerate(x["response"], x["hit_max"]) for x in rows), len(rows))
                if deg > Fraction(1, 10):
                    continue
                key = (-J, s, abs((L if L is not None else 20) - 20), L if L is not None else -1)
                if best is None or key < best[0]:
                    best = (key, L, s)
            got = sel[r][k]
            want = (best[1], best[2]) if best else (None, 0.0)
            check(f"{r} fold {k}: chosen setting", (got["layer"], got["strength"]) == want, f"got {got['layer']},{got['strength']} want {want}")

    print("5. test rows used their own fold's setting")
    bad = []
    for r in RATIOS:
        check(f"{r}: 70 test rows", len(test[r]) == 70)
        for i, row in test[r].items():
            st = sel[r][fold_of[i]]
            if st["strength"] == 0:
                if row["response"] != base[i]["response"]:
                    bad.append(row["key"])
            elif (row["layer"], row["strength"], str(row["fold"])) != (st["layer"], st["strength"], fold_of[i]):
                bad.append(row["key"])
    check("every test row matches its fold's selection", not bad, str(bad[:5]))

    print("6. counts, McNemar, Holm recomputed")
    S = json.load(open(O("stats.json")))
    fam = []
    for r in RATIOS:
        for out_name, ids, f in (("unanswerable answered (primary)", un, "answered"), ("answered", ans, "answered"),
                                 ("overlap-cited", ans, "overlap_cited")):
            b = sum(bool(base[i][f]) and not test[r][i][f] for i in ids)
            c = sum(not base[i][f] and bool(test[r][i][f]) for i in ids)
            fam.append((r, out_name, sum(bool(test[r][i][f]) for i in ids), b, c, mcnemar(b, c)))
    hp = holm([x[-1] for x in fam])
    for (r, o, n, b, c, p), h, t in zip(fam, hp, S["tests"]):
        same = (t["ratio"], t["outcome"], t["steered"], t["only_baseline"], t["only_steered"]) == (r, o, n, b, c) \
            and abs(t["p"] - p) < 1e-12 and abs(t["p_holm"] - h) < 1e-12
        check(f"{r} {o}: steered {n}, {b}/{c}, p {p:.4f}, Holm {h:.4f}", same)

    print("7. blind sheet coverage (key not read)")
    want = set()
    for rows in [base] + [test[r] for r in RATIOS]:
        for i, row in rows.items():
            if qd[i]["type"] == "answerable" and row["answered"]:
                want.add((qd[i]["question"], E.strip_citations(row["response"]).strip()))
    with open(O("blind_sheet_blank.csv"), encoding="utf-8-sig", newline="") as f:
        got = {(x["question"], x["model_answer"].strip()) for x in csv.DictReader(f)}
    check("blind sheet = distinct answered answerable answers", got == want, f"sheet {len(got)}, expected {len(want)}")

    print(f"\n{'ALL CHECKS PASSED' if not FAIL else f'{len(FAIL)} CHECK(S) FAILED: {FAIL}'}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
