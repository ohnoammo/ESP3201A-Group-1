# Human read of the answered unanswerables (Clifton, 12 Nov 2026, 13:00–13:45)

**For James.** This file goes with `exp2_baselines_report.md`, Task 1. **It is a post-hoc reading, not a rescoring:** the pre-registered result (F0 5 vs P0 13 vs CB 18 of 18; F0 vs P0 Holm p 0.023) stands as written. Raw rows are in `unanswerable_read_unblinded.csv`.

## How the read was done
- **The sample:** all 36 answered unanswerables (F0 5, P0 13, CB 18), shuffled (sha256 `42:arm:id`) with the arm hidden. The key was opened only after Clifton finished. Claude suggested a category and note for each row; Clifton decided.
- **Categories:**
  - **invented reason:** a reason the evidence doesn't support;
  - **what-as-why:** restates the change as if it were the reason;
  - **premise denial:** claims the change didn't happen, or did the opposite. The questions describe real changes, so this is a false claim too;
  - **refusal:** says the reason isn't given (the scorer missed it);
  - **other:** grounded in the MR text on a question whose no_reason label is debatable;
  - **correct by luck:** states the real reason without seeing it.

## Result

| Category | F0 (grounded) | P0 (plain RAG) | CB (closed-book) |
|---|---|---|---|
| invented reason | 2 | 3 | 10 |
| what-as-why | 1 | 1 | 1 |
| premise denial | 0 | 4 | 7 |
| other (grounded, debatable label) | 2 | 4 | 0 |
| refusal (missed by the scorer) | 0 | 1 | 0 |
| correct by luck | 0 | 0 | 0 |
| **answered, pre-registered** | **5** | **13** | **18** |

**Refined hallucination counts, out of 18** (exact McNemar, two-sided, post hoc, unadjusted):

| Definition | F0 | P0 | CB | F0 vs P0 (b/c, p) | F0 vs CB (b/c, p) |
|---|---|---|---|---|---|
| **Confident false claim** = invented + what-as-why + premise denial (recommended) | **3** | **8** | **18** | 1/6, p 0.125 | 0/15, p 0.0001 |
| Invented + what-as-why only | 3 | 4 | 11 | 1/2, p 1.0 | 1/9, p 0.021 |
| Everything except refusals | 5 | 12 | 18 | 0/7, p 0.016 | 0/13, p 0.0002 |

## Reading for the report
1. **Grounding vs closed-book:** this result is robust. Without context the 4B produced a false claim for all 18 unanswerables (10 invented, 7 premise denials). With our grounded prompt it did so for 3, under every definition.
2. **Grounding vs plain RAG:** same direction, but not significant after a human read. False claims fall from 8 to 3. The pre-registered "13" includes 4 grounded answers on debatable labels and 1 refusal. Report the pre-registered Holm p 0.023, then this read.
3. **The kind of error changes:**
   - **Premise denial is the plain-RAG failure mode:** 4 of P0's 13, and 0 of F0's. Given context, the plain prompt often "corrects" the user with a related but different fact from a neighbouring MR. For example, it cited a different setting's 5 s–5 min backoff to deny the 5 s cap, and minimum-API checks to deny the older API pin.
   - The grounded prompt's "cite or say Not found" rule seems to turn these into refusals.
   - **Closed-book fails by both invention and denial.** Some of it is plainly fabricated: "Windows Server 2020", "9252 is the Kubernetes Metrics Server port".
4. **Label problems:** 6 of the 36 are grounded answers on debatable no_reason labels:
   - nr3177 and nr4460, the two already known (both F0 and P0 answered them from the MR text);
   - nr1372 and nr1781 (P0 only).

   They count as hallucinations in the pre-registered outcome but shouldn't. Add nr1372 and nr1781 to the limits section next to nr3177 and nr4460.
