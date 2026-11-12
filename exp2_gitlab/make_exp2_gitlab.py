"""Writes exp2_gitlab.py from exp2_sympy.py by exact replacements, so every change from the frozen
SymPy script is listed here and nothing else differs. Each replacement must match, or it stops.
Adds arm C1 (the app's final setting: fixed 512/77 + code links alpha 1); F0 stays as the no-links
control. Only one chunking, because the final setting uses only fixed."""
SRC, OUT = "exp2_sympy.py", "exp2_gitlab.py"
t = open(SRC, encoding="utf-8").read()


def sub(old, new, count=1):
    global t
    assert t.count(old) >= 1 and (count == 0 or t.count(old) == count), (old, t.count(old))
    t = t.replace(old, new)


sub('REPO = "sympy/sympy"', 'REPO = "gitlab-org/gitlab-runner"')
sub('POOL = "A2000"', 'POOL = "A270"')
sub('OUT = "exp2_sympy"', 'OUT = "exp2_gitlab"')
sub('"qwen3-embedding-0.6b_swe.npz"', '"qwen3_gitlab.npz"')
sub('"pull requests in the SymPy project"', '"pull requests in the GitLab Runner project"')
sub('a SymPy pull request', 'a GitLab Runner pull request', 0)
sub("'Django' -> 'SymPy'", "'Django' -> 'GitLab Runner'")
sub('https://github.com/{REPO}/pull/{n}', 'https://gitlab.com/{REPO}/-/merge_requests/{n}')
sub('https://github.com/{REPO}/pull/{r[\'pr_number\']}', 'https://gitlab.com/{REPO}/-/merge_requests/{r[\'pr_number\']}')
sub('startswith("doc/")', 'startswith("docs/")')
sub('"split": "sympy"', '"split": "gitlab-runner"')
sub('''CHUNKINGS = {"fixed_s512_o77": {"name": "fixed_s512_o77", "method": "fixed", "size": 512, "overlap": 77},
             "struct_c256": {"name": "struct_c256", "method": "structural", "cap": 256}}''',
    '''CHUNKINGS = {"fixed_s512_o77": {"name": "fixed_s512_o77", "method": "fixed", "size": 512, "overlap": 77}}''')
sub('''ARMS = {"F0": ("fixed_s512_o77", "score"), "S0-G": ("struct_c256", "grouped")}''',
    '''ARMS = {"F0": ("fixed_s512_o77", "score"), "C1": ("fixed_s512_o77", "score")}
ARM_ALPHA = {"F0": 0.0, "C1": 1.0}''')
sub('def pack(cand_ids, chunk_by_id, order, exclude_prs=()):', 'def pack(cand_ids, chunk_by_id, order, exclude_prs=(), alpha=ALPHA, links=None):')
sub('packed = expand_and_pack(ranked, ALPHA, {}, {}, BUDGET, ntok)', 'packed = expand_and_pack(ranked, alpha, links or {}, chunk_by_id, BUDGET, ntok)')
sub('''        by_id = {c["chunk_id"]: c for c in chunks}
        path = os.path.join(OUT, f"gen_{arm}.jsonl")''',
    '''        by_id = {c["chunk_id"]: c for c in chunks}
        alpha = ARM_ALPHA[arm]
        from relations import build_links
        links = build_links(chunks, {str(k): v for k, v in docs.items()}, kinds=("code",)) if alpha else {}
        path = os.path.join(OUT, f"gen_{arm}.jsonl")''')
sub('cks = pack(cands[q["id"]]["chunk_ids"], by_id, order, q["exclude_prs"])',
    'cks = pack(cands[q["id"]]["chunk_ids"], by_id, order, q["exclude_prs"], alpha, links)')
sub('"chunking": ch, "order": order, "alpha": ALPHA, "budget": BUDGET,', '"chunking": ch, "order": order, "alpha": alpha, "budget": BUDGET,')
open(OUT, "w", encoding="utf-8").write(t)
print("wrote", OUT)
