## The PR Explainer application

PR Explainer is a local web application that answers "why was this changed?" questions about a repository's pull requests. It runs on one computer; its only network calls go to a local Ollama instance. It uses the final configuration chosen from Experiments 1 and 2: dense retrieval over fixed 512-token chunks with relation links (α = 1 on pool A), a 2,560-token context budget, Qwen3 4B-Instruct and the strict grounded prompt v3 (temperature 0, seed 42). This exact combination was not evaluated end to end, because Experiment 2 used fixed chunks without links. Each answer cites the excerpts it used, and the Sources panel highlights the cited passage (Figure 1). When the excerpts state no reason, strict mode declines to answer (Figure 2). SymPy and GitLab Runner are also available, but they use Django's settings unchanged and untuned, so those answers are exploratory.

Two features are design elements for future work, not results. First, users can rate an answer or report a problem type (Figure 3). Reports are appended to a local log for human review before any reuse (e.g. regression tests); the application does not learn from it. Second, an optional "experimental support check" applies the Experiment 2 MiniCheck gate unchanged (minimum score over cited sentences, threshold 0.5) to strict-mode answers only. It holds back answers that score below the threshold or cite no excerpt, behind a "Show anyway" button (Figure 4). It is off by default and experimental, because its AUROC on Django was near chance (about 0.54–0.57).

## Figure captions

**Figure 1** (`fig_app_answer.png`). A strict-mode answer to an answerable Django test question (q16966), with its citation chip and the Sources panel open on the cited excerpt, whose supporting passage is highlighted.

**Figure 2** (`fig_app_notfound.png`). For a Django test question whose pull request states no reason (nr14500), strict grounding declines to answer and points the user to the retrieved excerpts.

**Figure 3** (`fig_app_feedback.png`). The feedback controls under an answer, with the four report types shown (wrong answer, invented reason, borrowed from another PR, describes what, not why), which are logged for human review only.

**Figure 4** (`fig_app_supportcheck.png`). The Settings drawer with the experimental support check switched on, next to an answer that passed the check (q16966) and one that was held back with its score and a "Show anyway" button (q8596).
