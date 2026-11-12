You're picking up the GitLab Runner validation for ESP3201A. I'm James, the owner, though this account's email is Alyssa's. "GitLab runner" means the gitlab-org/gitlab-runner repo used as a transfer test, not a CI runner. Results are exploratory and don't go in the Exp 2 Findings.

Read these first:
1. C:\Users\kwekt\ESP3201A_local\gitlab_runner_copy\HANDOVER.md (state, results, traps)
2. tuning_rule_exp1_scale.md in the same folder, as the pattern for a rule file
3. The reporting and hard rules at the top of ESP3201A_Exp2\HANDOVER.md, in the ESP3201A project folder

Work only in gitlab_runner_copy. The gitlab_runner_validation folder in OneDrive is a snapshot, so don't run from it. Re-copy results there afterwards, leaving out prs, chunks, emb_cache, .git and exp2_gitlab/keys, and keep Answered_csvs.

The task is to scale Exp 2 past pool A270. Nothing has been generated yet. First:
1. Make sure the repo is committed.
2. Check the handover's scaling traps against the code.
3. Draft tuning_rule_exp2_scale.md and stop for my sign-off before any generation. It needs these decisions from me, each with your recommendation:
   - the pool and number of questions, given what two people can label
   - who writes the questions and who checks them
   - arms and models (the pilot used F0 and C1 on 4B with prompt v3)
   - whether the pilot's 15 questions are kept out
   - whether the MiniCheck gate runs
   - tests or counts only, and which is primary, fixed before any result

Keep these fixed:
- Don't change settings or tune on this data.
- The pilot's files stay as they are; the scaled run gets its own output folder.
- Don't compare results with Django as if like for like, because the data and labels differ.
- Don't open exp2_gitlab/keys/ or use it to label answers.
- People label blind. Alyssa is the reference rater.

Don't paste diffs or file contents in chat. Tell me which files and which sections or rows changed, and why. Check for problems before trusting a result, and if advice I paste from Claude chat conflicts with the data, check it and tell me.
