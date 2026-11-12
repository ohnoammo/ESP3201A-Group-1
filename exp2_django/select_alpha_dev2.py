"""Apply tuning_rule_dev2.md to the dev2 retrieval-only grid.

    python eval_links.py --split dev2 --packer exp1 --links exp2      # grid, all alphas
    python select_alpha_dev2.py                                        # -> results/alpha_selection_dev2.json
"""
import json

GRID = (0.0, 0.25, 0.5, 1.0)
TOL = 0.02


def main():
    with open("results/links_eval_dev2_exp1pack_exp2.json", encoding="utf-8") as f:
        ev = json.load(f)
    out = {"rule": "tuning_rule_dev2.md", "source": "results/links_eval_dev2_exp1pack_exp2.json",
           "git_commit_of_eval": ev.get("git_commit"), "chosen": {}, "table": {}}
    for ch in ("fixed_s512_o77", "struct_c256"):
        arms = {a: ev["arms"][f"{ch}|a={a if a not in (0.0, 1.0) else int(a)}"] for a in GRID}
        base = arms[0.0]["gold_pr_in_ctx"]
        rows = []
        for a in GRID:
            m = arms[a]
            ok = m["gold_pr_in_ctx"] >= base - TOL - 1e-9
            rows.append({"alpha": a, "any_span": m["any_cov"], "gold_pr_in_budget": m["gold_pr_in_ctx"],
                         "linked": m["mean_linked"], "eligible": ok})
        best = None
        for r in rows:                                  # ascending alpha -> ties keep the smaller
            if r["eligible"] and (best is None or r["any_span"] > best["any_span"] + 1e-9):
                best = r
        out["table"][ch] = rows
        out["chosen"][ch] = best["alpha"]
    with open("results/alpha_selection_dev2.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
