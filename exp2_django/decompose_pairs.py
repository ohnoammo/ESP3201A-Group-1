"""Discordant-pair breakdowns behind two McNemar results (4B-instruct, test answerables, v3).

    python decompose_pairs.py      # -> results/decompose_pairs.json (+ printed tables)

(1) F0/v3 vs S0/v3, overlap-cited: for questions right in one arm only, what the other arm did:
    abstained / empty / no valid citation (no ids, or an id not in its context) / valid citations
    but no gold chunk, split into "same PR" (cites a chunk of the question's PR) vs "other PR only".
    "gold cited + invalid id" = a gold chunk cited alongside an id not in the context.
(2) S0-G/v3 vs S-0.25/v3, overlap-cited only in S-0.25: for each gold chunk S-0.25 cited,
    whether it entered the context by retrieval or by a link (expand_and_pack's "linked" flag:
    its best offer came through a link), its retrieval rank in the top-100, and the link type(s)
    from the best-ranked retrieved chunk that links to it (link_map.py types).
"""
import json
import re

from common import read_jsonl
from pack_exp1 import _candidates, _links
from run_generation import pack_context, short_id
from score import auto

GEN = "results/gen_test_arms_4b-instruct.jsonl"
ARM = {"F0": "pack-fixed-0-score", "S0": "pack-struct-0-score", "S0-G": "pack-struct-0-grouped",
       "S-0.25": "pack-struct-0.25-grouped"}
CITE = re.compile(r"PR(\d+)-c(\d+)")
LINK_NAME = {"hunk->thread": "hunk-thread", "thread->hunk": "hunk-thread",
             "parent": "part-title/description", "conv_prev": "conversation neighbour",
             "conv_next": "conversation neighbour"}


def gold_of(q, rec):
    ch = rec["pack"]["chunking"]
    return {short_id(c) for c in q.get(f"overlap_chunks_{ch}") or []}


def what_happened(rec, q):
    a = auto(rec, q)
    if a["abstained"]:
        return "abstained"
    if a["empty_answer"]:
        return "empty"
    cites = [f"PR{x}-c{y}" for x, y in CITE.findall(rec["response"])]
    shown = set(rec["context_short_ids"])
    valid = [c for c in cites if c in shown]
    if not valid:
        return "no valid citation"
    if any(c in gold_of(q, rec) for c in valid):
        return "gold cited + invalid id"
    if any(c.startswith(f"PR{q['pr_number']}-") for c in valid):
        return "wrong chunk, same PR"
    return "wrong chunk, other PR only"


def main():
    qs = {q["id"]: q for q in read_jsonl("questions_test_arms.jsonl")}
    ids = sorted(i for i, q in qs.items() if q["type"] == "answerable" and q["split"] == "test")
    rec = {}
    for r in read_jsonl(GEN):
        ctx, pk = r["condition"].split(":")
        if pk == "c3" and r["id"] in ids:
            rec[(ctx, r["id"])] = r
    out = {}

    # (1)
    def right(arm, i):
        return auto(rec[(ARM[arm], i)], qs[i])["overlap_cited"]
    for a, b in (("F0", "S0"), ("S0", "F0")):
        rows = []
        for i in ids:
            if right(a, i) and not right(b, i):
                r = rec[(ARM[b], i)]
                gold = gold_of(qs[i], r)
                rows.append({"id": i, b: what_happened(r, qs[i]),
                             "gold_in_context": bool(gold & set(r["context_short_ids"]))})
        out[f"{a} overlap-cited, {b} not"] = rows
        print(f"\n{a} overlap-cited, {b} not: n={len(rows)}")
        for k in sorted({x[b] for x in rows}):
            sub = [x for x in rows if x[b] == k]
            print(f"  {k:28} {len(sub):>2}  (gold chunk in {b} context: {sum(x['gold_in_context'] for x in sub)})")

    # (2)
    cands, _ = _candidates("struct_c256")
    raw = _links("struct_c256")
    rows = []
    for i in ids:
        if right("S-0.25", i) and not right("S0-G", i):
            r, q = rec[(ARM["S-0.25"], i)], qs[i]
            cks, _ = pack_context(q, ARM["S-0.25"])
            by_short = {short_id(c["chunk_id"]): c for c in cks}
            ranked = cands[i]["chunk_ids"]
            g0 = rec[(ARM["S0-G"], i)]
            for sid in sorted({f"PR{x}-c{y}" for x, y in CITE.findall(r["response"])} & gold_of(q, r)):
                c = by_short[sid]
                cid = c["chunk_id"]
                rank = ranked.index(cid) + 1 if cid in ranked else None
                types, src = [], None
                if c["linked"]:
                    for rr, s in enumerate(ranked, 1):
                        t = [LINK_NAME[lt] for tgt, lt in raw.get(s, []) if tgt == cid]
                        if t:
                            types, src = sorted(set(t)), (short_id(s), rr)
                            break
                rows.append({"id": i, "chunk": sid, "how": "link" if c["linked"] else "retrieved",
                             "retrieval_rank": rank, "link_from": src, "link_types": types,
                             "in_S0-G_context": sid in g0["context_short_ids"],
                             "S0-G": what_happened(g0, q)})
    out["S-0.25 overlap-cited, S0-G not"] = rows
    print(f"\nS-0.25 overlap-cited, S0-G not: {len({x['id'] for x in rows})} questions")
    for x in rows:
        print(f"  {x['id']:10} {x['chunk']:12} {x['how']:9} rank={x['retrieval_rank']} "
              f"from={x['link_from']} types={x['link_types']} inS0G={x['in_S0-G_context']} S0-G={x['S0-G']}")
    with open("results/decompose_pairs.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
