"""Final Exp 2 result tables in one markdown file (queue e; no new computation).

    python make_results_tables.py      # -> results/exp2_results_tables.md

Sections: Findings; (1) setup and question sets; (2) frozen arms: answered, overlap-cited, abstention,
unanswerable; (3) correctness, judge agreement, drift check; (4) faithfulness, gate, AUROC; (5) failure
analysis; (6) PR length and arm W-F (exploratory); (7) arm H0 (hybrid); (8) SymPy transfer check
(exploratory, counts only); (9) Limitations. Every test is
labelled with its family: primary 60, contain 20, correctness 40, hybrid 16, or exploratory / unadjusted.
Findings numbers are read from the result files. The Findings list is owner-approved (1-8 on 1 Nov; 9, arm
H0, on 5 Nov, which raised the cap from 8 to 9).
Reads (results/): summary_test_arms.csv, stats_test_arms.csv, stats_test_arms_contain.csv,
v2v3_mitigation(_excl15).csv, correctness_test_arms.csv, stats_correctness.csv, agreement_validation.json,
codex_drift_check.json, summary_faithfulness.csv, gate_eval(_excl15).csv, gate_auroc(_excl15).csv,
gate_auroc_correctness.csv, failure_examples.json, pr_length_pool.json, wholepr_fit.json,
summary_test_arm_W.csv, summary_faithfulness_W.csv, w_correctness.csv, w_comparisons.csv,
w_comparisons_lenient_sensitivity.csv, w_subset.csv, w_gate.csv; gen_test_arm_W_8b.jsonl (citation style);
summary_test_arm_H0.csv, retrieval_H0_vs_F0_summary.json, correctness_H0.csv, stats_hybrid.csv,
stats_hybrid_lenient.csv, summary_faithfulness_H0(_unanswerable).csv, summary_faithfulness_unanswerable.csv,
gate_H0.csv, codex_drift_check_h.json, limit_hybrid.csv, limit_hybrid_coverage.csv, sympy_transfer.csv,
sympy_agreement.json, sympy_exp1_compare.csv, sympy_exp1_dense_vs_hybrid.csv; judging/codex_pack.csv and codex_labels.csv (H0 duplicate-answer check).
"""
import csv
import json
import re
from collections import defaultdict

from common import git_commit, read_jsonl
from stats_correctness import norm

MODEL = {"qwen3:4b-instruct-2507-q4_K_M": "4B", "qwen3:8b": "8B", "4b-instruct": "4B", "8b": "8B"}
ORDER = ["F0", "S0", "S0-G", "S-0.25"]
NOMINAL = [("4b-instruct", "F0/v2", "S0/v2"), ("4b-instruct", "F0/v3", "S0/v3"),
           ("4b-instruct", "S0-G/v3", "S-0.25/v3")]

LIMITATIONS = """## 9. Limitations

- **Cited vs full-context premises are not a paired estimate (P6).** Each claim's MiniCheck score is
  its maximum over windows. Full contexts make more windows than cited contexts, so they get more
  chances at a high maximum, while support that spans separated chunks can be split across windows;
  HHEM sees one long premise. In the full run cited minus full > 0.1 in 169/658 (MiniCheck) and
  126/658 (HHEM) rows. Cited and full scores are reported as two premise conditions, cited primary;
  no context-benefit claim is made from their difference.
- **The faithfulness measure is sentence-level support (P7).** MiniCheck and HHEM score whether each
  answer sentence is supported by the premise. A sentence can be supported by the PR without being
  the reason for the change, and an omitted or wrong causal link is not detected. Correctness
  (right reason) is judged separately (blind Codex labels, Alyssa's validation sample).
- **Sentence extraction is rule-based (P8).** Answers are split on `.`, `!` or `?` followed by
  whitespace, so abbreviations such as "e.g." can split a sentence, and fragments under 3 words are
  dropped. Either can change the minimum sentence score the gate uses; the effect on gate decisions
  has not been measured.
- **Correctness judge.** Correctness labels are from one LLM judge (Codex, blind to model, arm and
  prompt; citations removed), primary for every correctness table and test. They are checked
  against one independent human rater (Alyssa, reference; blind to Codex labels, model and
  condition) on n = {n} rows (10 per model x prompt x chunking stratum): 3-label Cohen's kappa
  {k3} [{k3lo}, {k3hi}], strict (correct vs rest) {ks} [{kslo}, {kshi}], lenient (correct or partial
  vs wrong) {kl} [{kllo}, {klhi}]. Codex is stricter on correct vs partial ({cp} of the {nd}
  disagreements: Alyssa correct, Codex partial); Alyssa is stricter on wrong ({aw} of {nd}: Alyssa
  wrong, Codex correct or partial; the reverse, Alyssa partial / Codex wrong, {cw}). Strict
  correctness may therefore run low compared with a human judge. The lenient kappa CI is wide
  because Alyssa labelled only {nwrong} rows wrong. One human rater and {n} rows; there is no second
  human rater.
- **Same-ticket PRs in the pool.** {nst} of the 50 answerable gold PRs have a same-ticket PR in pool A
  (Exp 1's same-ticket filter covered its fixing PRs only). A same-ticket PR may legitimately contain
  the reason, so citing one is not always borrowing. Codex judged against the gold only (q15435:
  partial). The pool is frozen; the effect is seen on 1 question, {stc} answered rows.
- **Arm W-F is exploratory.** It was proposed after the test results were seen
  (`tuning_rule_wholepr.md`), sits outside every Holm family, and its comparisons carry unadjusted p
  only. Its ceiling is lower: answer span in context {wspan}/50 vs {f0span} (F0) and 43-44 (structural
  arms), because only the rank-1 PR may be truncated and gold PRs over 2,560 units at lower ranks are
  skipped. W faithfulness is not comparable with the chunk arms: whole-PR premises are longer, so
  MiniCheck takes the max over more windows and HHEM reads past 512 tokens. 8B's chunk-style citations
  (`[PR<n>-c<k>]`, {w8c} of {w8n} 8B citations) are a prompt-format artefact (the frozen prompts' example
  id); they count as PR n.
- **Cross-session Codex drift (W-F labels).** The W-F rows were labelled in a later Codex session. 20 old
  ids re-judged in that session: {dagree}/20 agree (kappa {dk}); all {nchg} changes are partial -> correct
  ({chg}). Strict W-F counts may therefore be slightly lenient compared with the frozen arms. One
  duplicate answer went the other way (J0652 frozen, correct; J0715 W-F, partial). Lenient counts are
  unaffected by partial/correct changes. Drift labels are not used in any analysis.
- **Arm H0 was proposed after the frozen results.** It has its own Holm family (hybrid 16) and changes
  no frozen arm. Its rows were labelled in a later Codex session than F0 and have no human validation.
  20 old ids re-judged in that session: {hagree}/20 agree (kappa {hk}); changes: {hchg}. {hnconf} duplicate-answer
  groups that include an H0 row got different labels ({hconf}); they are reported and not relabelled.
  Power is low: surviving Holm takes at least 10 discordant pairs all one way (stated in
  `tuning_rule_hybrid.md` before any data), so a non-significant result is not evidence of no effect.
- **SymPy is a small transfer check, not a replication.** 15 answerable and 7 unanswerable questions, one model
  and prompt, no tests, and no hybrid arm or gate output in its Exp 2. Its labels are from two human raters
  (lower label kept), while Django's are from Codex, which was stricter than Alyssa on correct vs partial, so
  strict counts are not like-for-like across projects. All {sdis} rater disagreements are on S0-G, so the F0 vs
  S0-G strict order depends on the merge rule. It ran on a different GPU from the Django runs.
- **Curated question set (P9).** 50 answerable test questions, one per shortlisted PR, with
  questions and gold answers written by Claude and reviewed by James and Codex. Verbatim span checks
  show the quotes exist; they do not show that every clause of each gold answer is needed or fully
  supported. The set favours PRs with an explicit, rationale-rich discussion and is not a
  representative sample of Django PRs.
- **Gate threshold timing (P1).** Threshold 0.5 specified in planning before the full faithfulness
  run (only a 30-row check existed). The rule file was committed after
  results/summary_faithfulness.csv (2da7d48 before 074812c). The sweep (0.1-0.9) is shown; 0.5 is
  not presented as a confirmatory result.
"""


def rd(name):
    with open(f"results/{name}", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def js(name):
    with open(f"results/{name}", encoding="utf-8") as f:
        return json.load(f)


def table(head, rows):
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + \
        ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def rng(xs):
    xs = [int(x) for x in xs]
    return f"{min(xs)}-{max(xs)}" if min(xs) != max(xs) else str(min(xs))


def frange(xs):
    xs = [float(x) for x in xs]
    return f"{min(xs):.2f}-{max(xs):.2f}"


def h0_label_conflicts():
    """Same question and normalised answer, different labels, at least one H0 row (J0793 onwards)."""
    with open("judging/codex_labels.csv", newline="", encoding="utf-8-sig") as fh:
        labels = {r["blind_id"]: r["label"].strip().lower() for r in csv.DictReader(fh)}
    groups = defaultdict(list)
    with open("judging/codex_pack.csv", newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            groups[(r["question"], norm(r["model_answer"]))].append(r["blind_id"])
    return [ids for ids in groups.values()
            if len({labels[b] for b in ids}) > 1 and any(int(b[1:]) >= 793 for b in ids)]


def main():
    s = sorted(rd("summary_test_arms.csv"), key=lambda r: (MODEL[r["model"]], r["prompt"], ORDER.index(r["arm"])))
    st = {(r["model"], r["A"], r["B"], r["outcome"]): r for r in rd("stats_test_arms.csv")}
    sc = {(r["model"], r["A"], r["B"], r["outcome"]): r for r in rd("stats_test_arms_contain.csv")}
    sk = {(r["model"], r["A"], r["B"], r["outcome"]): r for r in rd("stats_correctness.csv")}
    assert len(st) == 60 and len(sc) == 20 and len(sk) == 40
    c = sorted(rd("correctness_test_arms.csv"), key=lambda r: (MODEL[r["model"]], r["prompt"], ORDER.index(r["arm"])))
    v, v15 = rd("v2v3_mitigation.csv"), rd("v2v3_mitigation_excl15.csv")
    ag, dr, fx = js("agreement_validation.json"), js("codex_drift_check.json"), js("failure_examples.json")
    f = rd("summary_faithfulness.csv")
    g, g15 = rd("gate_eval.csv"), rd("gate_eval_excl15.csv")
    au, au15, ac = rd("gate_auroc.csv"), rd("gate_auroc_excl15.csv"), rd("gate_auroc_correctness.csv")
    pl, wfit = js("pr_length_pool.json"), js("wholepr_fit.json")
    ws = rd("summary_test_arm_W.csv")
    wfa = {(r["model"], r["prompt"]): r for r in rd("summary_faithfulness_W.csv")}
    wc = {(r["model"], r["prompt"]): r for r in rd("w_correctness.csv")}
    wg = {(r["model"], r["prompt"]): r for r in rd("w_gate.csv")}
    wsub, wcomp, wlen = rd("w_subset.csv"), rd("w_comparisons.csv"), rd("w_comparisons_lenient_sensitivity.csv")
    qs = read_jsonl("questions_test_arms.jsonl")

    # ---------- Findings (numbers read from the files above)
    hmin = {k: min(float(r["p_holm"]) for r in fam.values()) for k, fam in
            (("primary 60", st), ("contain 20", sc), ("correctness 40", sk))}
    un = {m: [r["unanswerable_answered_of17"] for r in s if MODEL[r["model"]] == m] for m in ("4B", "8B")}
    un15 = {m: [r["unanswerable_answered_of15"] for r in s if MODEL[r["model"]] == m] for m in ("4B", "8B")}
    v4 = [r for r in v if MODEL[r["model"]] == "4B"]
    v8 = [r for r in v if MODEL[r["model"]] == "8B"]
    corr = {m: [r for r in c if MODEL[r["model"]] == m] for m in ("4B", "8B")}
    fmin = [r["minicheck_cited_min"] for r in f]
    f0_top = all(max((r for r in f if (r["model"], r["prompt"]) == (m, p)),
                     key=lambda r: float(r["minicheck_cited_min"]))["arm"] == "F0"
                 for m, p in {(r["model"], r["prompt"]) for r in f})
    gsum = {k: sum(int(r[k]) for r in g) for k in ("answered_ungated", "answered_gated", "overlap_cited_ungated",
                                                     "overlap_cited_gated", "unanswerable_answered_ungated_of17",
                                                     "unanswerable_answered_gated_of17")}
    gclued = gsum["unanswerable_answered_gated_of17"] - sum(int(q["unanswerable_answered_gated_of15"]) for q in g15)
    aua = {(r["model"], r["judge"]): r for r in au if r["arms"] == "all" and r["negatives"] == "all_answered"}
    acx = {(r["model"], r["judge"]): r for r in ac if r["arms"] == "all" and r["negatives"] == "correct"}
    ci = lambda r: f"{r['auroc']} [{r['ci_lo']}, {r['ci_hi']}]"  # noqa: E731
    f0sub = [r for r in wsub if r["comparison"] == "W-F vs F0"]
    dstrict = [int(r["W_strict"]) - int(r["other_strict"]) for r in f0sub]
    dlen = [int(r["W_lenient"]) - int(r["other_lenient"]) for r in f0sub]
    f0span = next(r["span_in_ctx"] for r in s if r["arm"] == "F0")
    wspan = ws[0]["span_in_ctx"]
    gl = wfit["gold_pr_lengths_exp1_units"]
    assert len({r["span_in_ctx"] for r in s if r["arm"] == "F0"}) == 1 and len({r["span_in_ctx"] for r in ws}) == 1
    f0_any_sig = any(float(r["p_unadjusted"]) < 0.05 for r in wcomp if r["comparison"] == "W-F vs F0")
    dd = ag["disagreement_directions"]
    cpl = {}                                    # mean Exp 1 units per context chunk, by chunking
    for m in ("4b-instruct", "8b"):
        for r in read_jsonl(f"results/gen_test_arms_{m}.jsonl"):
            cpl.setdefault(r["pack"]["chunking"], []).append(r["pack"]["tokens"] / len(r["context_chunk_ids"]))
    cpl = {k: sum(x) / len(x) for k, x in cpl.items()}
    assert cpl["fixed_s512_o77"] > cpl["struct_c256"]
    f0has = {r["id"]: r["span_in_context"]["any"] for r in read_jsonl("results/gen_test_arms_4b-instruct.jsonl")
             if r["condition"] == "pack-fixed-0-score:c" and r["type"] == "answerable" and r["split"] == "test"}
    lost = [r for r in rd("wholepr_fit_per_question.csv") if r["chunking"] == "fixed" and r["type"] == "answerable"
            and r["gold_span_in_context"] != "True" and f0has[r["id"]]]
    big = lambda r: int(r["gold_tokens"]) > 2560  # noqa: E731
    lb = {"big_trunc": sum(big(r) and r["gold_status"] == "truncated_rank1" for r in lost),
          "big_skip": sum(big(r) and r["gold_status"] == "skipped" for r in lost),
          "small_skip": sum(not big(r) and r["gold_status"] == "skipped" for r in lost)}
    assert sum(lb.values()) == len(lost) and len(f0has) == 50
    assert all(int(r["gold_rank_pr"]) > 1 for r in lost if not big(r))        # skipped behind higher-ranked PRs
    h9_ret, h9_t = js("retrieval_H0_vs_F0_summary.json"), rd("stats_hybrid.csv")
    h9_un = [r for r in h9_t if r["outcome"] == "unanswerable answered /17"]
    h9_st = [r for r in h9_t if r["outcome"] == "strict correct /50"]
    h9_min = min(float(r["p_holm"]) for r in h9_t)
    assert h9_min >= 0.05 and all(int(r["H0"]) > int(r["F0"]) for r in h9_st), "reword finding 9 by hand"
    findings = [
        f"1. **No arm or prompt difference survives Holm in its family** (smallest Holm p: primary 60 "
        f"{hmin['primary 60']}, contain 20 {hmin['contain 20']}, correctness 40 {hmin['correctness 40']}). "
        f"Differences between arms are counts only. *Caveat:* 50 answerable questions; a few questions either way "
        f"is noise.",
        f"2. **8B answers more unanswerable questions than 4B** in every arm and prompt: {rng(un['8B'])} of 17 vs "
        f"{rng(un['4B'])} (15-question sensitivity: {rng(un15['8B'])} vs {rng(un15['4B'])}). "
        f"*Caveat:* 17 questions, counts only, no test.",
        "3. **Prompt v3 lowers 4B's unanswerable answers in every arm** (" + ", ".join(
            f"{r['arm']} {r['unanswerable_answered_v2']}->{r['unanswerable_answered_v3']}" for r in v4) +
        f"); 8B changes by {rng([abs(int(r['unanswerable_answered_v2']) - int(r['unanswerable_answered_v3'])) for r in v8])}. "
        f"*Caveat:* unadjusted p {min(float(r['unanswerable_answered_p']) for r in v4):g}-"
        f"{max(float(r['unanswerable_answered_p']) for r in v4):g}; no single test reaches p < 0.05.",
        f"4. **Correctness (Codex):** strict {rng([r['correct'] for r in corr['4B']])} of 50 (4B) and "
        f"{rng([r['correct'] for r in corr['8B']])} (8B); lenient "
        f"{rng([int(r['correct']) + int(r['partial']) for r in corr['4B']])} and "
        f"{rng([int(r['correct']) + int(r['partial']) for r in corr['8B']])}. Codex vs Alyssa (n = {ag['n']}): kappa "
        f"{ag['kappa_3class']} {ag['kappa_3class_ci95']}. *Caveat:* counts only, no Holm survivor in the correctness "
        f"40 family; one LLM judge checked by one human rater. Codex is stricter than Alyssa on correct vs partial "
        f"({dd['human_correct_codex_partial']} of {sum(dd.values())} disagreements), so strict rates may run low; "
        f"lenient is less affected.",
        f"5. **Sentence-level support** (MiniCheck cited min, mean per stratum) ranges {frange(fmin)}"
        + (" and is highest for F0 in every model x prompt" if f0_top else "") +
        ". *Caveat:* a support proxy, not the right reason; no test. Fixed cited chunks are longer than structural "
        f"ones (mean context chunk {cpl['fixed_s512_o77']:.0f} vs {cpl['struct_c256']:.0f} Exp 1 units), so support "
        "is not comparable across chunkings.",
        f"6. **Gate at 0.5** keeps {gsum['answered_gated']}/{gsum['answered_ungated']} answered answerables, "
        f"{gsum['overlap_cited_gated']}/{gsum['overlap_cited_ungated']} overlap-cited answers and "
        f"{gsum['unanswerable_answered_gated_of17']}/{gsum['unanswerable_answered_ungated_of17']} unanswerable answers "
        f"({gclued} of them from nr9172 and nr13883). *Caveat:* threshold set in planning, rule file committed after "
        f"the faithfulness results (P1).",
        f"7. **Discrimination (AUROC, unanswerable answers as positives):** vs all answered answerables, MiniCheck "
        f"{ci(aua[('4b-instruct', 'minicheck')])} (4B) and {ci(aua[('8b', 'minicheck')])} (8B), HHEM "
        f"{ci(aua[('4b-instruct', 'hhem')])} and {ci(aua[('8b', 'hhem')])}; vs judged-correct answers, HHEM "
        f"{ci(acx[('4b-instruct', 'hhem')])} and {ci(acx[('8b', 'hhem')])}, MiniCheck {ci(acx[('4b-instruct', 'minicheck')])} "
        f"and {ci(acx[('8b', 'minicheck')])}. *Caveat:* PR-family bootstrap with few positive families; HHEM above "
        f"MiniCheck is a point-estimate difference with overlapping CIs and no paired test; the gate keeps MiniCheck "
        f"(test-set result, no rule change).",
        f"8. **Arm W-F (exploratory):** whole-PR packing has the answer span in context on "
        f"{int(f0span) - int(wspan)} fewer questions than F0 ({wspan} vs {f0span} of 50). Of the {len(lost)} questions "
        f"where F0 has it and W-F does not, {lb['big_trunc'] + lb['big_skip']} have a gold PR over the 2,560 budget "
        f"({lb['big_trunc']} truncated at rank 1, {lb['big_skip']} skipped) and {lb['small_skip']} have a smaller gold "
        f"PR skipped because higher-ranked PRs filled the budget. On the {f0sub[0]['n_both_span']} questions with the answer span in context for both, W-F was "
        f"correct on {min(dlen)}-{max(dlen)} more questions than F0 under lenient labels, and "
        f"{min(dstrict)}-{max(dstrict)} more under strict labels, which cross-session label drift can affect. "
        + ("Some" if f0_any_sig else "No") + " pre-declared W-F vs F0 test reaches p < 0.05. *Caveat:* exploratory "
        "arm proposed after the test results; descriptive subset.",
        f"9. **Arm H0 (hybrid; proposed after the frozen results):** gold PR in the top 5 PRs "
        f"{h9_ret['gold_pr_top5']['H0']} vs {h9_ret['gold_pr_top5']['F0']} of 50, with no sign of the Exp 1 drop. "
        "No evidence of a reduction in hallucination (unanswerable answered "
        + ", ".join(f"{r['F0']}->{r['H0']}" for r in h9_un) +
        f"). Strict correct rises in all four cells, but no test survives Holm in the hybrid 16 family (smallest Holm p "
        f"{h9_min:.3f}). *Caveat:* 50 + 17 questions; H0 labels come from a later Codex session and have no human "
        "validation.",
    ]

    out = ["# Exp 2 results (test arms): final tables", "",
           f"Generated by `make_results_tables.py` at {git_commit()} from the files in `results/`. "
           "Test families: **primary 60** (Holm over 60 exact McNemar tests, `stats_test_arms.csv`), "
           "**contain 20** (Holm over 20, `stats_test_arms_contain.csv`), **correctness 40** (Holm over 40, "
           "`stats_correctness.csv`, `tuning_rule_correctness.md`), **hybrid 16** (Holm over 16, arm H0 vs F0, "
           "`stats_hybrid.csv`, `tuning_rule_hybrid.md`), **exploratory / unadjusted** (everything else, "
           "including v2 -> v3 on unanswerables and all arm W-F tests). No arm is called best.", "",
           "## Findings", ""] + findings + [""]

    # ---------- (1) setup
    from collections import Counter
    qc = Counter((q["type"], q["split"]) for q in qs)
    out += ["## 1. Setup and question sets", "",
            "Pool: Exp 1 pool A with the same-ticket filter (2,231 PRs: 231 fixing + 2,000 distractors). Retriever: "
            "Exp 1 dense (Qwen3-Embedding-0.6B), saved top-100 candidates per chunking. Packing: Exp 1 "
            "`relations.expand_and_pack`, budget 2,560 Exp 1 units. Models: qwen3:4b-instruct-2507-q4_K_M (4B), qwen3:8b "
            "(8B); Ollama 0.40.4, temperature 0, seed 42, num_ctx 8192. Prompts: v2 (`c`) and v3 (`c3`, \"a WHAT is not "
            "a WHY\"), frozen.", ""] + table(
        ["arm", "chunking / ranking", "alpha", "order", "status"],
        [["F0", "fixed 512/77", "0", "score", "frozen"], ["S0", "structural c256", "0", "score", "frozen"],
         ["S0-G", "structural c256", "0", "grouped by PR", "frozen"],
         ["S-0.25", "structural c256", "0.25 (dev2)", "grouped by PR", "frozen"],
         ["W-F", "fixed 512/77 ranking; whole parent PRs", "-", "rank", "exploratory (section 6)"]]) + [""] + table(
        ["question set", "n", "use"],
        [["answerable (test)", qc[("answerable", "test")], "answered, overlap-/contain-cited, correctness, faithfulness"],
         ["no-reason (test)", qc[("no_reason", "test")], "unanswerable"],
         ["no-reason (dev)", qc[("no_reason", "dev")], "unanswerable"],
         ["whole PR excluded (test)", qc[("removed", "test")], "unanswerable"],
         ["answer removed, PR kept", qc[("removed_kept", "test")], "rk16129 and rk9789 in the 17 unanswerables "
                                                                    "(case studies); rk11459, rk12342 dropped"]]) + \
        ["", "Unanswerable: 17 primary (5 no-reason test + 5 no-reason dev + 5 whole PR excluded + rk16129 + rk9789); "
         "15 = without nr9172 and nr13883 (sensitivity, P3). Abstention: strict rule (`score.abstained_strict`).", ""]

    # ---------- (2) frozen arms
    out += ["## 2. Frozen arms: answered, citation, abstention, unanswerable", "",
            "**Overlap-cited:** >= 1 citation, all valid, >= 1 cited chunk overlaps a gold span. **Contain-cited:** "
            "a cited chunk fully contains a gold span (49 questions; q14748 has no such structural chunk).", ""] + table(
        ["model", "prompt", "arm", "answered /50", "overlap-cited /50", "contain-cited /49", "q14748 overlap-cited",
         "abstained with span /50", "unanswerable answered /17", "/15 (sensitivity)"],
        [[MODEL[r["model"]], r["prompt"], r["arm"], r["answered"], r["overlap_cited"], r["contain_cited_of49"],
          r["q14748_overlap_cited"], r["abstained_with_span"], r["unanswerable_answered_of17"],
          r["unanswerable_answered_of15"]] for r in s]) + [""]
    rows = []
    for m, a, b in NOMINAL:
        o, cc = st[(m, a, b, "overlap_cited")], sc[(m, a, b, "contain_cited")]
        rows.append([MODEL[m], f"{a} vs {b}", f"{o['only_A']}/{o['only_B']}", o["p"], o["p_holm"],
                     f"{cc['only_A']}/{cc['only_B']}", cc["p"], cc["p_holm"]])
    out += ["### Citation McNemar tests (exact, paired; b = only A, c = only B)", ""] + table(
        ["model", "pair", "overlap b/c", "p", "Holm p (primary 60)", "contain b/c", "p", "Holm p (contain 20)"],
        rows) + [""]
    nom = sorted((r for r in st.values() if float(r["p"]) < 0.05), key=lambda r: float(r["p"]))
    out += ["Every primary-60 test with p < 0.05 (family: primary 60; none has Holm p < 0.05):", ""] + table(
        ["model", "A vs B", "outcome", "b/c", "p", "Holm p (primary 60)"],
        [[MODEL[r["model"]], f"{r['A']} vs {r['B']}", r["outcome"], f"{r['only_A']}/{r['only_B']}", r["p"],
          r["p_holm"]] for r in nom]) + [""]
    out += ["### Prompt v2 -> v3 (family: exploratory / unadjusted for unanswerables; overlap-cited p unadjusted here, "
            "its Holm p is in the primary 60)", ""] + table(
        ["model", "arm", "unanswerable /17 v2 -> v3 (b/c, p)", "/15 (sensitivity)", "overlap-cited /50 v2 -> v3 (b/c, p)"],
        [[MODEL[r["model"]], r["arm"],
          f"{r['unanswerable_answered_v2']} -> {r['unanswerable_answered_v3']} "
          f"({r['unanswerable_answered_b']}/{r['unanswerable_answered_c']}, {r['unanswerable_answered_p']})",
          f"{q['unanswerable_answered_v2']} -> {q['unanswerable_answered_v3']} "
          f"({q['unanswerable_answered_b']}/{q['unanswerable_answered_c']}, {q['unanswerable_answered_p']})",
          f"{r['overlap_cited_v2']} -> {r['overlap_cited_v3']} "
          f"({r['overlap_cited_b']}/{r['overlap_cited_c']}, {r['overlap_cited_p']})"] for r, q in zip(v, v15)]) + [""]

    # ---------- (3) correctness
    out += ["## 3. Correctness and judge agreement", "",
            "Codex labels, blind; unanswered = not correct. Strict = correct; lenient = correct or partial. "
            "Counts only: no correctness test has Holm p < 0.05 (family: correctness 40).", ""] + table(
        ["model", "prompt", "arm", "answered /50", "correct", "partial", "wrong", "strict /50", "lenient /50",
         "correct of overlap-cited"],
        [[MODEL[r["model"]], r["prompt"], r["arm"], r["answered"], r["correct"], r["partial"], r["wrong"],
          int(r["correct"]), int(r["correct"]) + int(r["partial"]),
          f"{r['correct_of_overlap_cited']}/{r['overlap_cited']}"] for r in c]) + [""]
    pairs = list(dict.fromkeys(k[:3] for k in sk))
    out += ["### Correctness McNemar tests (exact, paired; family: correctness 40)", ""] + table(
        ["model", "pair", "strict b/c", "p", "Holm p (correctness 40)", "lenient b/c", "p", "Holm p (correctness 40)"],
        [[MODEL[m], f"{a} vs {b}"] + [x for o in ("correct", "correct_or_partial") for x in
                                       (f"{sk[(m, a, b, o)]['only_A']}/{sk[(m, a, b, o)]['only_B']}",
                                        sk[(m, a, b, o)]["p"], sk[(m, a, b, o)]["p_holm"])]
         for m, a, b in pairs]) + [""]
    ps = sorted(sk.values(), key=lambda r: float(r["p"]))
    out += [f"Tests with p < 0.05: {sum(float(r['p']) < 0.05 for r in ps)} of 40. Smallest p: "
            f"{MODEL[ps[0]['model']]} {ps[0]['A']} vs {ps[0]['B']} {ps[0]['outcome']} "
            f"{ps[0]['only_A']}/{ps[0]['only_B']} p={ps[0]['p']} (Holm p {ps[0]['p_holm']}).", ""]
    cf = ag["confusion_rows_human_cols_codex"]
    out += [f"### Codex vs Alyssa (independent reference rater), n = {ag['n']}", "",
            "Row bootstrap 95% CIs (2,000 resamples, seed 0). Specific agreement = 2 n_ii / (row_i + col_i).", ""] + table(
        ["measure", "kappa [95% CI]", "raw agreement"],
        [["3 labels", f"{ag['kappa_3class']} {ag['kappa_3class_ci95']}", ag["raw_agreement"]],
         ["strict: correct vs rest", f"{ag['kappa_strict']} {ag['kappa_strict_ci95']}", ag["agreement_strict"]],
         ["lenient: correct or partial vs wrong", f"{ag['kappa_lenient']} {ag['kappa_lenient_ci95']}",
          ag["agreement_lenient"]]]) + [""] + table(
        ["Alyssa (rows) / Codex (cols)", "correct", "partial", "wrong", "specific agreement"],
        [[h] + [cf[h][k] for k in ("correct", "partial", "wrong")] + [ag["per_class_specific_agreement"][h]]
         for h in ("correct", "partial", "wrong")]) + [""]
    out += ["Disagreements by direction (Alyssa -> Codex): " + "; ".join(
        f"{k.replace('human_', '').replace('_codex_', ' -> ')} {val}" for k, val in ag["disagreement_directions"].items()) +
        ". List: `agreement_disagreements.csv`.", ""]
    out += ["### Codex drift check (20 old ids re-judged in the W-F session; not used in any analysis)", ""] + table(
        ["n", "agree", "kappa (3 labels)", "changes"],
        [[dr["n"], dr["agree"], dr["kappa_3class"],
          "; ".join(f"{x['blind_id']} {x['original']} -> {x['rejudged']}" for x in dr["changes"])]]) + [""]

    # ---------- (4) faithfulness, gate, AUROC
    out += ["## 4. Faithfulness, gate and discrimination", "",
            "### Faithfulness (sentence-level support; cited chunks primary; no tests)", ""] + table(
        ["model", "arm", "prompt", "n", "MiniCheck cited min", "all supported", "HHEM cited min", "MiniCheck full min",
         "HHEM full min"],
        [[MODEL[r["model"]], r["arm"], r["prompt"], r["n"], r["minicheck_cited_min"], r["minicheck_cited_all_supported"],
          r["hhem_cited_min"], r["minicheck_full_min"], r["hhem_full_min"]] for r in f]) + [""]
    out += ["### Gate (MiniCheck cited min < 0.5 -> abstain), ungated -> gated (no tests)", ""] + table(
        ["model", "arm", "prompt", "answered /50", "overlap-cited", "unanswerable /17", "unanswerable /15 (sensitivity)"],
        [[MODEL[r["model"]], r["arm"], r["prompt"], f"{r['answered_ungated']} -> {r['answered_gated']}",
          f"{r['overlap_cited_ungated']} -> {r['overlap_cited_gated']}",
          f"{r['unanswerable_answered_ungated_of17']} -> {r['unanswerable_answered_gated_of17']}",
          f"{q['unanswerable_answered_ungated_of15']} -> {q['unanswerable_answered_gated_of15']}"]
         for r, q in zip(g, g15)]) + [""]
    out += [f"{gclued} of the {gsum['unanswerable_answered_gated_of17']} gate-passed unanswerable rows come from "
            "nr9172 and nr13883.", ""]
    out += ["### AUROC, answered unanswerable (positives) vs answered answerables (negatives)", "",
            "95% CI: bootstrap by PR family (1,000 reps, seed 42). Overlap-cited negatives are a conditional contrast; "
            "all-answered negatives are the deployment population; correct negatives use Codex labels.", ""] + table(
        ["model", "arms", "negatives", "judge", "pos rows (families)", "neg rows (families)", "AUROC [95% CI], 17",
         "AUROC [95% CI], 15 (sensitivity)"],
        [[MODEL[r["model"]], r["arms"], r["negatives"], r["judge"], f"{r['n_pos_rows']} ({r['n_pos_families']})",
          f"{r['n_neg_rows']} ({r['n_neg_families']})", ci(r), f"{ci(q)} (pos {q['n_pos_rows']})"]
         for r, q in zip(au, au15)] +
        [[MODEL[r["model"]], r["arms"], r["negatives"], r["judge"], f"{r['n_pos_rows']} ({r['n_pos_families']})",
          f"{r['n_neg_rows']} ({r['n_neg_families']})", ci(r), "-"] for r in ac if r["negatives"] == "correct"]) + [""]

    # ---------- (5) failure analysis
    out += ["## 5. Failure analysis", "",
            "One example per category; fixed selection rule; full table with explanations in "
            "`results/failure_analysis.md`. Categories are not exclusive, so counts do not sum.", ""] + table(
        ["category", "example", "model / arm / prompt", "count / population", "source"],
        [[e["category"], (e["example"] or {}).get("id", "-") + (" (repeat)" if e.get("repeat_of_used_question") else ""),
          " / ".join(str(MODEL.get(val, val)) for val in ((e["example"] or {}).get(k, "-") for k in ("model", "arm", "prompt"))),
          e["count"] + ("; " + e["count_other_side"] if e.get("count_other_side") else ""), e["source"]]
         for e in fx["table"]]) + [""]

    # ---------- (6) PR length and W-F
    pa = pl["pool_a_lengths"]
    fx_fit = wfit["fit"]["fixed"]["answerable_50"]
    out += ["## 6. PR length and arm W-F (exploratory)", "",
            "### PR length (Exp 1 units)", ""] + table(
        ["set", "n", "median", "p90", "max", "> 512", "> 2,560"],
        [["pool A", pa["n"], pa["median"], pa["p90"], pa["max"], pa["over_512"], pa["over_2560"]]] +
        [[k, x["n"], x["median"], x["p90"], x["max"], x["over_512"], x["over_2560"]] for k, x in gl.items()]) + [""]
    out += ["### Whole-PR fit in 2,560 (50 answerables; fixed ranking = W-F; structural shown for reference only)", ""] + table(
        ["ranking", "PRs packed median (range)", "gold whole", "gold truncated at rank 1", "gold skipped",
         "gold not retrieved", "answer span in context: W vs frozen"],
        [[k, f"{x['answerable_50']['prs_packed_median']} ({x['answerable_50']['prs_packed_range'][0]}-"
             f"{x['answerable_50']['prs_packed_range'][1]})"] +
         [x["answerable_50"]["gold"][s_] for s_ in ("whole", "truncated_rank1", "skipped", "not_retrieved")] +
         [f"{x['answerable_50']['gold_span_in_context_W']} vs " + ", ".join(
             f"{a} {n}" for a, n in x["answerable_50"]["frozen_span_in_context"].items())]
         for k, x in wfit["fit"].items()]) + [""]
    assert fx_fit["gold_span_in_context_W"] == int(wspan)
    out += ["### Arm W-F results (`tuning_rule_wholepr.md`; proposed after the test results; family: exploratory / "
            "unadjusted)", "",
            "Gold-PR-cited: answered, >= 1 citation, all cited PRs shown, >= 1 is the gold PR. Faithfulness uses the "
            "cited whole PR(s) and is not comparable with the chunk arms.", ""] + table(
        ["model", "prompt", "answered /50", "gold-PR-cited /50", "answer span in context /50", "strict /50",
         "lenient /50", "correct of answered", "unanswerable answered /17", "MiniCheck cited min", "HHEM cited min"],
        [[MODEL[r["model"]], r["prompt"], r["answered"], r["gold_pr_cited"], r["span_in_ctx"],
          wc[(r["model"], r["prompt"])]["strict_of50"], wc[(r["model"], r["prompt"])]["lenient_of50"],
          wc[(r["model"], r["prompt"])]["correct_of_answered"], r["unanswerable_answered_of17"],
          wfa[(r["model"], r["prompt"])]["minicheck_cited_min"], wfa[(r["model"], r["prompt"])]["hhem_cited_min"]]
         for r in ws]) + [""]
    out += ["Pre-declared comparisons (exact McNemar; b = only W-F, c = only the other arm; family: exploratory / "
            "unadjusted). W-F vs F0: same ranking, packing only (primary exploratory). W-F vs S-0.25: ranking and "
            "packing differ (descriptive context, not a packing effect). The last rows are the lenient sensitivity, "
            "added after the drift check.", ""] + table(
        ["model", "prompt", "comparison", "outcome", "W-F", "other", "b/c", "p (unadjusted)"],
        [[MODEL[r["model"]], r["prompt"], r["comparison"], r["outcome"], r["W_count"], r["other_count"],
          f"{r['b_only_W']}/{r['c_only_other']}", r["p_unadjusted"]] for r in wcomp] +
        [[MODEL[r["model"]], r["prompt"], r["comparison"], r["outcome"] + " (sensitivity)", r["W_count"],
          r["other_count"], f"{r['b_only_W']}/{r['c_only_other']}", r["p_unadjusted"]] for r in wlen]) + [""]
    out += ["Questions with the answer span in context in both arms (counts only):", ""] + table(
        ["model", "prompt", "comparison", "n", "strict W-F", "strict other", "lenient W-F", "lenient other",
         "answered W-F", "answered other"],
        [[MODEL[r["model"]], r["prompt"], r["comparison"], r["n_both_span"], r["W_strict"], r["other_strict"],
          r["W_lenient"], r["other_lenient"], r["W_answered"], r["other_answered"]] for r in wsub]) + [""]
    out += ["Gate on W-F (exploratory; kept = cited min >= 0.5; HHEM shown for comparison, no rule change):", ""] + table(
        ["model", "prompt", "answerables kept MiniCheck", "correct kept MiniCheck", "answerables kept HHEM",
         "correct kept HHEM", "unanswerables kept MiniCheck", "unanswerables kept HHEM"],
        [[MODEL[m], p, f"{r['answerable_kept_minicheck']}/{r['answerable_answered']}",
          f"{r['answerable_correct_kept_minicheck']}/{r['answerable_correct_ungated']}",
          f"{r['answerable_kept_hhem']}/{r['answerable_answered']}",
          f"{r['answerable_correct_kept_hhem']}/{r['answerable_correct_ungated']}",
          f"{r['unanswerable_kept_minicheck']}/{r['unanswerable_answered']}",
          f"{r['unanswerable_kept_hhem']}/{r['unanswerable_answered']}"] for (m, p), r in wg.items()]) + [""]

    # ---------- (7) arm H0
    cells = [("4B", "v2"), ("4B", "v3"), ("8B", "v2"), ("8B", "v3")]
    h_auto = {"F0": {(MODEL[r["model"]], r["prompt"]): r for r in s if r["arm"] == "F0"},
              "H0": {(MODEL[r["model"]], r["prompt"]): r for r in rd("summary_test_arm_H0.csv")}}
    h_corr = {(r["arm"], MODEL[r["model"]], r["prompt"]): r for r in rd("correctness_H0.csv")}
    h_tests, h_len = rd("stats_hybrid.csv"), rd("stats_hybrid_lenient.csv")
    h_ret, h_dr = js("retrieval_H0_vs_F0_summary.json"), js("codex_drift_check_h.json")
    h_gate = {(r["arm"], MODEL[r["model"]], r["prompt"]): r for r in rd("gate_H0.csv")}
    h_faith = {"answered answerable": {"F0": f, "H0": rd("summary_faithfulness_H0.csv")},
               "answered unanswerable": {"F0": rd("summary_faithfulness_unanswerable.csv"),
                                         "H0": rd("summary_faithfulness_H0_unanswerable.csv")}}
    assert len(h_tests) == 16
    h_min = min(float(r["p_holm"]) for r in h_tests)
    assert h_min >= 0.05, "a hybrid 16 test survives Holm: reword by hand per tuning_rule_hybrid.md"
    h_conf = h0_label_conflicts()
    arrow = lambda fn: ", ".join(f"{a} {p} {fn('F0', a, p)} -> {fn('H0', a, p)}" for a, p in cells)  # noqa: E731
    h_aut = lambda k: lambda arm, a, p: h_auto[arm][(a, p)][k]  # noqa: E731
    h_cor = lambda k: lambda arm, a, p: h_corr[(arm, a, p)][k]  # noqa: E731
    strict = [r for r in h_tests if r["outcome"] == "strict correct /50"]

    def h_gtot(arm, grp):
        rows_ = [h_gate[(arm, a, p)] for a, p in cells]
        return f"{sum(int(r[f'{grp}_kept_minicheck']) for r in rows_)}/{sum(int(r[f'{grp}_answered']) for r in rows_)}"
    out += ["## 7. Arm H0 (hybrid retrieval; family: hybrid 16)", "",
            "H0 = F0 with one change: the ranking is Exp 1's hybrid retriever (RRF of code-aware BM25 and dense, k = 60) "
            "instead of dense alone. Same pool, chunks, packing (alpha 0, budget 2,560), prompts and models; 67 questions, "
            "268 rows. Rule: `tuning_rule_hybrid.md`, committed before any hybrid run. No arm is called best.", "",
            "### How the research question is answered", "",
            f"- **Context relevance:** gold PR in the first 5 ranked PRs {h_ret['gold_pr_top5']['F0']} (F0) vs "
            f"{h_ret['gold_pr_top5']['H0']} (H0) of 50; answer span in context {h_ret['span_in_ctx']['F0']} vs "
            f"{h_ret['span_in_ctx']['H0']}. Counts only; no sign of the Exp 1 drop.",
            f"- **Hallucination:** no evidence of a reduction, and none of an increase. Unanswerable answered /17: "
            f"{arrow(h_aut('unanswerable_answered_of17'))}. Answered and judged wrong /50: "
            f"{arrow(h_cor('answered_wrong_of50'))}. Gate at 0.5 keeps {h_gtot('H0', 'unanswerable')} unanswerable answers "
            f"for H0 and {h_gtot('F0', 'unanswerable')} for F0, and {h_gtot('H0', 'answerable')} and "
            f"{h_gtot('F0', 'answerable')} answered answerables. These are the supporting counts, with no test.",
            f"- **Correctness (pre-declared outcome):** strict correct /50: "
            f"{arrow(h_cor('strict_of50'))}. Unadjusted p {min(float(r['p']) for r in strict):g}-"
            f"{max(float(r['p']) for r in strict):g}; no test survives Holm (smallest Holm p across the family {h_min:g}), "
            f"so a correctness difference is not supported under the strict and lenient rule.",
            "- *Caveats:* 50 + 17 questions; H0 labels come from a later Codex session than F0; the arm was proposed "
            "after the frozen results.", "",
            "### Retrieval, 50 answerables (counts only, `retrieval_H0_vs_F0.csv`)", ""] + table(
        ["measure", "F0", "H0", "only F0", "only H0"],
        [["gold PR in first 5 ranked PRs", h_ret["gold_pr_top5"]["F0"], h_ret["gold_pr_top5"]["H0"],
          ", ".join(h_ret["top5_lost"]) or "-", ", ".join(h_ret["top5_gained"]) or "-"],
         ["answer span in context", h_ret["span_in_ctx"]["F0"], h_ret["span_in_ctx"]["H0"],
          ", ".join(h_ret["span_lost"]) or "-", ", ".join(h_ret["span_gained"]) or "-"]]) + [""]
    out += [f"H0 and F0 have identical contexts on {sum(h_ret['identical_contexts_of67'].values())} of the "
            "67 x 4 rows, so the rule's identical-context check for non-determinism and label drift has no rows.", "",
            "### Counts, F0 -> H0", ""] + table(
        ["model", "prompt", "answered /50", "overlap-cited /50", "abstained with span", "strict /50", "lenient /50",
         "answered wrong /50", "unanswerable answered /17", "unanswerable answered /15"],
        [[a, p] + [f"{h_auto['F0'][(a, p)][k]} -> {h_auto['H0'][(a, p)][k]}"
                   for k in ("answered", "overlap_cited", "abstained_with_span")] +
         [f"{h_corr[('F0', a, p)][k]} -> {h_corr[('H0', a, p)][k]}"
          for k in ("strict_of50", "lenient_of50", "answered_wrong_of50")] +
         [f"{h_auto['F0'][(a, p)][k]} -> {h_auto['H0'][(a, p)][k]}"
          for k in ("unanswerable_answered_of17", "unanswerable_answered_of15")] for a, p in cells]) + [""]
    out += ["### McNemar tests (exact, paired; b = only H0, c = only F0; family: hybrid 16)", ""] + table(
        ["model", "prompt", "outcome", "F0", "H0", "b/c", "p", "min attainable p", "Holm p"],
        [[MODEL[r["model"]], r["prompt"], r["outcome"], r["F0"], r["H0"], f"{r['b_only_H0']}/{r['c_only_F0']}", r["p"],
          r["min_p"], r["p_holm"]] for r in h_tests]) + [""]
    out += ["Lenient correct /50 (sensitivity, family: exploratory / unadjusted, not in hybrid 16):", ""] + table(
        ["model", "prompt", "F0", "H0", "b/c", "p (unadjusted)"],
        [[MODEL[r["model"]], r["prompt"], r["F0"], r["H0"], f"{r['b_only_H0']}/{r['c_only_F0']}", r["p_unadjusted"]]
         for r in h_len]) + [""]
    out += ["### Faithfulness (mean of row minimum, cited chunks primary; no tests)", ""] + table(
        ["rows", "arm", "model", "prompt", "n", "MiniCheck cited min", "all supported", "HHEM cited min"],
        [[grp, arm, MODEL[r["model"]], r["prompt"], r["n"], r["minicheck_cited_min"], r["minicheck_cited_all_supported"],
          r["hhem_cited_min"]]
         for grp, by in h_faith.items() for arm, rows_ in by.items() for r in rows_ if r["arm"] == arm]) + [""]
    out += ["### Gate at 0.5 (kept = cited min >= 0.5; MiniCheck is the rule, HHEM shown for comparison; no tests)", ""] + table(
        ["model", "prompt", "arm", "answerables kept MiniCheck", "correct kept", "wrong kept", "unanswerables kept MiniCheck",
         "answerables kept HHEM", "unanswerables kept HHEM"],
        [[a, p, arm, f"{r['answerable_kept_minicheck']}/{r['answerable_answered']}",
          f"{r['correct_kept_minicheck']}/{r['correct_ungated']}", f"{r['wrong_kept_minicheck']}/{r['wrong_ungated']}",
          f"{r['unanswerable_kept_minicheck']}/{r['unanswerable_answered']}",
          f"{r['answerable_kept_hhem']}/{r['answerable_answered']}",
          f"{r['unanswerable_kept_hhem']}/{r['unanswerable_answered']}"]
         for a, p in cells for arm in ("F0", "H0") for r in [h_gate[(arm, a, p)]]]) + [""]
    h_lim, h_cov = rd("limit_hybrid.csv"), rd("limit_hybrid_coverage.csv")
    out += ["### Limit test: how large a change could there be? (`tuning_rule_hybrid_limit.md`; family: exploratory; "
            "written after the H0 counts were seen)", "",
            "Difference = H0 minus F0 in questions, so negative means fewer with H0. Cells: Newcombe paired score "
            "interval, 95%. Pooled: mean per cell, PR-family bootstrap. There is no pass/fail margin, and these limits "
            "do not show that the arms are equivalent. A fall cannot exceed the F0 count.", ""] + table(
        ["outcome", "scope", "model", "prompt", "F0", "H0", "b/c", "difference", "95% limits"],
        [[r["outcome"], r["scope"], MODEL.get(r["model"], r["model"]), r["prompt"], r["F0"] or "-", r["H0"] or "-",
          f"{r['b_only_H0']}/{r['c_only_F0']}" if r["F0"] else "-", r["diff_questions"],
          f"{r['lower_limit_questions']} to {r['upper_limit_questions']}"] for r in h_lim]) + [""]
    h_c17 = [float(r["coverage"]) for r in h_cov if r["n"] == "17"]
    h_c50 = [float(r["coverage"]) for r in h_cov if r["n"] == "50"]
    out += [f"Exact coverage of the cell interval at the checked rates (nominal 0.95): n = 17 {min(h_c17):.3f}-{max(h_c17):.3f}, "
            f"n = 50 {min(h_c50):.3f}-{max(h_c50):.3f}. The lowest values are below nominal, so the limits may be slightly "
            "narrow (`limit_hybrid_coverage.csv`).", ""]
    out += ["### Codex drift check and duplicate answers (H0 session; drift labels not used in any analysis)", ""] + table(
        ["n", "agree", "kappa (3 labels)", "changes"],
        [[h_dr["n"], h_dr["agree"], h_dr["kappa_3class"],
          "; ".join(f"{x['blind_id']} {x['original']} -> {x['rejudged']}" for x in h_dr["changes"])]]) + [""]
    out += [f"Duplicate answers that include an H0 row and got different labels: {len(h_conf)} "
            "(" + "; ".join(", ".join(ids) for ids in h_conf) + "). Reported, not relabelled.", ""]

    # ---------- (8) SymPy transfer check
    sy = {r["arm"]: r for r in rd("sympy_transfer.csv")}
    sy_ag, sy_cmp = js("sympy_agreement.json"), rd("sympy_exp1_compare.csv")
    sy_p = rd("sympy_exp1_dense_vs_hybrid.csv")
    dj = {r["arm"]: r for r in s if MODEL[r["model"]] == "4B" and r["prompt"] == "v3" and r["arm"] in sy}
    djc = {r["arm"]: r for r in c if MODEL[r["model"]] == "4B" and r["prompt"] == "v3" and r["arm"] in sy}
    assert all(int(sy[a]["n_answerable"]) == 15 and int(sy[a]["n_unanswerable"]) == 7 for a in sy)
    cmp_ = {(r["project"], r["condition"]): r for r in sy_cmp}
    conds = list(dict.fromkeys(r["condition"] for r in sy_cmp))
    short = lambda x: " ".join(x.split("|")[:2])  # noqa: E731
    out += ["## 8. SymPy transfer check (Clifton; exploratory, counts only)", "",
            "Django's settings applied unchanged to a second project, decided before any SymPy result. Exp 1: 75 "
            "SWE-bench tasks + 2,000 other PRs. Exp 2: the 4B on prompt v3, arms F0 and S0-G, dense retrieval, on 15 "
            "answerable and 7 unanswerable hand-checked questions. Inputs and hashes are in `results/sympy/`; "
            "`import_sympy.py` recounts them against Clifton's files. No SymPy comparison is tested, and no arm is "
            "ranked on it. It is not in the Findings list.", "",
            "### Exp 1, full query (Hit@5 / MRR@5)", ""] + table(
        ["condition", "Django (n = 181)", "SymPy (n = 75)"],
        [[short(k), f"{cmp_[('Django', k)]['hit5']} / {cmp_[('Django', k)]['mrr5']}",
          f"{cmp_[('SymPy', k)]['hit5']} / {cmp_[('SymPy', k)]['mrr5']}"] for k in conds]) + [""]
    out += ["Dense vs hybrid within each project (unadjusted, as printed by Exp 1's `stats.py`; 0.000 is the rounded "
            "printed value):", ""] + table(
        ["project", "chunking", "Hit@5 McNemar p", "MRR@5 permutation p"],
        [[r["project"], r["A"].split("|")[0], r["hit5_mcnemar_p"], r["mrr5_permutation_p"]] for r in sy_p]) + [""]
    measures = [("answer span in context", lambda a: dj[a]["span_in_ctx"], "span_in_context", 50, 15),
                ("answered", lambda a: dj[a]["answered"], "answered", 50, 15),
                ("strict correct (SymPy: lower label)", lambda a: djc[a]["correct"], "correct_lower", 50, 15),
                ("strict correct (SymPy: upper label)", lambda a: djc[a]["correct"], "correct_upper", 50, 15),
                ("answered wrong (SymPy: lower label)", lambda a: djc[a]["wrong"], "wrong_lower", 50, 15),
                ("cross-PR borrowing", lambda a: dj[a]["cross_pr_borrowing"], "cross_pr_borrowing", 50, 15),
                ("unanswerable answered", lambda a: dj[a]["unanswerable_answered_of17"], "unanswerable_answered", 17, 7)]
    sy_len = lambda a, k: int(sy[a][f"correct_{k}"]) + int(sy[a][f"partial_{k}"])  # noqa: E731
    dj_len = lambda a: int(djc[a]["correct"]) + int(djc[a]["partial"])  # noqa: E731
    assert all(sy_len(a, "lower") == sy_len(a, "upper") for a in sy)
    out += ["### Exp 2, 4B on prompt v3 (Django vs SymPy; counts only)", ""] + table(
        ["measure", "F0 Django", "F0 SymPy", "S0-G Django", "S0-G SymPy"],
        [[name, f"{dj_f('F0')}/{dn}", f"{sy['F0'][key_]}/{sn}", f"{dj_f('S0-G')}/{dn}", f"{sy['S0-G'][key_]}/{sn}"]
         for name, dj_f, key_, dn, sn in measures] +
        [["lenient correct (both label rules agree)", f"{dj_len('F0')}/50", f"{sy_len('F0', 'lower')}/15",
          f"{dj_len('S0-G')}/50", f"{sy_len('S0-G', 'lower')}/15"]]) + [""]
    out += [f"Labels: Alyssa and James, blind and independent, {sy_ag['n']} answers; {sy_ag['agree']}/{sy_ag['n']} agree, "
            f"3-label kappa {sy_ag['kappa_3class']}, strict kappa {sy_ag['kappa_strict']}. All "
            f"{len(sy_ag['disagreements'])} disagreements are on S0-G ("
            + ", ".join(x["blind_id"] for x in sy_ag["disagreements"]) +
            "), so F0 vs S0-G on strict depends on the merge rule. The rule (lower label, upper as sensitivity) was "
            "set before the key was opened (`results/sympy/LABEL_MERGE_RULE.txt`).", "",
            "Unanswerable answers: F0 " + sy["F0"]["unanswerable_ids"].replace(" ", ", ") + "; S0-G "
            + sy["S0-G"]["unanswerable_ids"].replace(" ", ", ") + ". One no-reason question, nr17375, was dropped before "
            "generation because Alyssa's check found a reason stated in a code comment; a later reviewed sheet "
            "(`outputs/2026-11-05_question_check_review/`) still marks it as correctly classified.", ""]

    sh = rd("sympy_h0/correctness.csv")
    sh_c, sh_hw = js("sympy_h0/labels_check.json"), js("sympy_h0/hardware_control.json")
    assert not sh_c["disagreements"]
    out += ["### H0 on SymPy, 4B v3 (`tuning_rule_sympy_h0.md`; exploratory, counts only)", ""] + table(
        ["arm", "answer span /15", "answered /15", "overlap-cited /15", "strict /15", "lenient /15", "wrong /15",
         "unanswerable answered /7", "which"],
        [[r["arm"], r["span_in_context"], r["answered"], r["overlap_cited"], r["correct_lower"],
          int(r["correct_lower"]) + int(r["partial_lower"]), r["wrong_lower"], r["unanswerable_answered"],
          r["unanswerable_ids"].replace(" ", ", ")] for r in sh]) + [""]
    out += [f"H0 is compared with the F0 rerun on the same GPU. With identical contexts, {sh_hw['identical_answers']} of "
            f"{sh_hw['n']} F0 answers matched across GPUs, so a gap of a question or two can be hardware alone. The pattern "
            "seen on Django repeated in direction, on 15 + 7 questions, with no test. "
            f"Labels: two rater files, {sh_c['agree']}/{sh_c['n']} agree, and {sh_c['drift_F0_agree']}/{sh_c['drift_F0_n']} "
            "re-labelled F0 rows match the earlier labels. Agreement is higher than on the earlier sheet (20/24). "
            "The owner confirmed both files are independent human labels (5 Nov).", ""]

    # ---------- (9) limitations
    st_row = next(e for e in fx["table"] if e["category"] == "same-ticket")
    cites8 = [x for line in open("results/gen_test_arm_W_8b.jsonl", encoding="utf-8")
              for x in re.findall(r"PR\d+(-c\d+)?", json.loads(line)["response"])]
    out += [LIMITATIONS.format(
        n=ag["n"], k3=ag["kappa_3class"], k3lo=ag["kappa_3class_ci95"][0], k3hi=ag["kappa_3class_ci95"][1],
        ks=ag["kappa_strict"], kslo=ag["kappa_strict_ci95"][0], kshi=ag["kappa_strict_ci95"][1],
        kl=ag["kappa_lenient"], kllo=ag["kappa_lenient_ci95"][0], klhi=ag["kappa_lenient_ci95"][1],
        cp=dd["human_correct_codex_partial"], nd=sum(dd.values()),
        aw=dd["human_wrong_codex_correct"] + dd["human_wrong_codex_partial"],
        cw=dd["human_partial_codex_wrong"], nwrong=ag["human_counts"]["wrong"],
        wspan=wspan, f0span=f0span, w8c=sum(bool(x) for x in cites8), w8n=len(cites8),
        dagree=dr["agree"], dk=round(dr["kappa_3class"], 2), nchg=len(dr["changes"]),
        chg=", ".join(x["blind_id"] for x in dr["changes"]),
        hagree=h_dr["agree"], hk=round(h_dr["kappa_3class"], 2),
        hchg="; ".join(f"{x['blind_id']} {x['original']} -> {x['rejudged']}" for x in h_dr["changes"]),
        hnconf=len(h_conf), hconf="; ".join(", ".join(ids) for ids in h_conf),
        sdis=len(sy_ag["disagreements"]),
        nst=len(fx["pr_with_ticket_mates_in_pool"]), stc=st_row["count"].split(" answered")[0].replace(" ", ""))]
    with open("results/exp2_results_tables.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print("\n".join(findings))


if __name__ == "__main__":
    main()
