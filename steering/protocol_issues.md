# Protocol issues (Codex build)

Things in section 4 of `CODEX_README.md` that I think are wrong, risky or ambiguous, and what I did. I did
not silently change the protocol: where I had to choose, the choice is the smallest one and is recorded
here and in `design_choices.md`. Ordered by how much they could matter.

## 1. This "Codex" build was written by Claude, so the cross-check is weaker than planned

The README was written for OpenAI's Codex so that a different model would build an independent version.
Clifton asked Claude (Opus 5.5) to build it instead, under the Codex name. I did not open Claude's other
build, but both builds come from the same model family reading the same README, so they can share blind
spots (the same misreading of an ambiguous rule would appear in both and the comparison would not catch it).
**What I did:** built it independently anyway and wrote down every open choice. **Suggestion:** treat
agreement between the two builds as weaker evidence than agreement with a different model would be.

## 2. A single additive vector cannot be "refuse when evidence is absent, answer when present"

The `twin` pairs (chosen "Not found", rejected the gold answer) and the `g_nf` pairs (chosen the gold
answer, rejected "Not found") have mirror-image response texts. Activations are averaged over the response
tokens, which are dominated by the response text, so in the mean these two families largely cancel. What
survives is roughly (a) a refuse-vs-answer direction whose sign and size depend on the ratio, plus (b) a
smaller WHAT-vs-WHY component from `g_what`, plus whatever prompt-dependence the averaged activations carry.
An added vector is the same for every prompt, so at best it shifts the model towards refusing or towards
answering; it cannot make refusal depend on whether the evidence is present.
**Consequence:** the expected result is a trade-off (fewer unanswerables answered at the cost of fewer
answerables answered, or the reverse), with the ratio choosing the direction. J rewards both sides, so the
selection may often pick strength 0. **What I did:** implemented the protocol as written, and added to
`vector_info.json` the cosine between each vector's refusal part and grounding part (strongly negative
values confirm the cancellation) and the vector-to-residual norm ratio. The report should state this
limit rather than present a null result as "steering does not work".

## 3. Strengths 0.5, 1 and 2 of a raw mean difference may be too small (or too large) to act

The protocol fixes the strengths as multiples of the unnormalised mean difference. Because of item 2 the
mean difference may be small relative to the residual stream (in the CPU test with a 0.5B model and 4 pairs
it was 0.17 of the typical residual norm at layer 13 of 24, and strengths 0.5 to 2 left one test answer
unchanged while 4 flipped it; for the real vectors it is unknown until the run). If it is
small, all nine settings may behave like strength 0 and the experiment cannot show anything. **What I
did:** nothing to the grid; `vectors` prints the norm ratio for every fold, ratio and layer, and the
optional sweep shows the whole trade-off curve. If the ratios are tiny (say < 0.05), consider asking for a
second, pre-registered grid in units of residual norm before looking at held-out results.

## 4. Layer numbering is ambiguous

"Decoder layers 14, 20 and 25 (of 36)" can be read 0-based (HF module index) or 1-based. **What I did:**
0-based index into `model.model.layers`, i.e. the output of the 15th, 21st and 26th block
(`hidden_states[L + 1]`). If Claude's build used 1-based layers the two builds differ by one block.

## 5. The rejected and chosen texts are mostly off-policy

Gold answers were written by Claude; WHAT-as-WHY texts are a fixed template; only the 5 stored
unanswerable answers are real model errors, and those came from the q4_K_M Ollama model, not the bf16 HF
model that is steered. A vector built on these can pick up "Claude's phrasing vs the template" as much as
"reason vs restated change". **What I did:** nothing beyond reporting it; the protocol fixes the pair
sources. The flags in `pair_flags.json` list the pairs most likely to be mislabelled.

## 6. The inner J is doubly optimistic

The README notes that inner unanswerables also built the vector. The same holds for the 14 inner
answerables: their `g_nf`/`g_what` pairs are in the vector too (if the ratio subset includes them). **What I
did:** nothing; only held-out results are reported, and the report says the inner J is not a result.

## 7. Power

With 18 unanswerables and Holm over 9, the primary test needs about a 7–0 discordant split; with 5-fold
selection adding noise, a non-significant result is the likely outcome even if steering has some effect.
This is stated in the report's limits.

## 8. "Hits 512 tokens" and "4-word run repeated 6 or more times"

Both are ambiguous. **What I did:** `hit_max` = 512 new tokens with no end token (an answer that ends
exactly at token 512 is not degenerate); a 4-gram counts if it occurs 6 or more times anywhere in the text,
not necessarily back to back (the stricter reading would miss loops with filler between repeats).

## 9. "Largest subset with that ratio"

An exact 40:60 split is impossible for most pair counts. **What I did:** exact reduced ratios 2:3, 1:1, 3:2,
which drops at most a·b − 1 pairs (e.g. 60:40 uses 54 + 36 = 90 of 130 training pairs, because grounding is
the limit at 36 = 2 × 18 and refusal then needs 54). The alternative "closest achievable ratio using all
pairs of the scarcer family" would use a few more pairs but not an exact ratio.

## 10. Twin label can be wrong when another MR states the same reason

A twin's "Not found" is only right if no other MR in its context states the reason. The README asks for
flags, not removal, and pairs must be built by script only. **What I did:** excluded the `quote_elsewhere`
MRs too (none for these 52, so no effect), kept every pair, and flagged suspects in `pair_flags.json`:
`twin:q3239` (MR 3408, whose gold answer is nearly the same reason, is in its twin context: the known
duplicate-rationale pair) and two weaker lexical flags (`twin:q589`, `twin:q3246`).

## 11. Some unanswerable labels rest on borderline human judgements

4 of the 5 stored F0 rejections cite the question's own MR (`nr3177`, `nr1781`, `nr3805`, `nr4460`): the
model found text it took for a reason, and the `no_reason` label rests on James's reading that it is not.
HANDOVER also notes that `nr4102` and `nr1372` are borderline and that `q5853` was reclassified after its
answers were seen. These labels now feed the vector directly. **What I did:** flagged the four; no change.

## 12. A WHAT-as-WHY rejection can carry the reason

`rm3265`'s title contains "to ensure ..." and 4 other titles share reason words with the gold answer
(`rm4142`, `q2211`, `q3831`, `q6695`). For `rm3265` the MR is excluded, so "Not found" is still the right
chosen answer; for the grounding ones the rejected text is partly right. **What I did:** flagged, kept.

## 13. Response mask excludes the end-of-turn token (and the run time is long)

Run time: 3 ratios × 5 folds × 9 settings × ~28 inner questions = 3,834 inner answers, plus 70 baseline and
up to 210 test answers. At 2 to 3 s per answer on the RTX 5070 that is roughly 3 to 4 hours, more if
strong settings produce 512-token loops. The protocol's grid is per fold × ratio, so this cannot be cut
without changing it. Everything resumes after an interruption.

On the mask:

The README says "response tokens only" without saying whether `<|im_end|>` counts. **What I did:** excluded
it, so a one-sentence refusal is averaged over its own ~7 tokens only.

## 14. The Ollama chat template may differ from the HF one

The stored F0 answers came through Ollama's template for the model; the HF run uses the tokenizer's chat
template. **What I did:** the pipeline check (answer vs refuse agreement, HF unsteered vs Ollama F0) is in
`stats.json` and the report; a low agreement should be investigated before trusting any comparison with
Exp 2's numbers, though the steering tests themselves only compare HF with HF.

## 15. One rater for the secondary correctness

Clifton labels the blind sheet alone; Exp 2's own labels had kappa 0.177 between raters. The correctness
comparison is therefore weak and is reported unadjusted, as the protocol says.
