# Pilot slide examples (qwen3:4b-instruct-2507-q4_K_M, oracle context, results/gen_pilot_4b.jsonl)

## 1. Same oracle context: the standard prompt invents a reason, the grounded prompt abstains

**Question (nr11371, PR #11371):** Why did Django's PostgreSQL test requirements switch from psycopg2-binary to the psycopg2 package?

*PR #11371 only swaps the requirement line; neither the PR nor its commit gives a reason.*

**(b) standard RAG:**

> Django switched from `psycopg2-binary` to `psycopg2` in its test requirements to ensure compatibility and consistency with the official psycopg2 package. The change likely aims to provide more control over the installation process and to avoid potential issues with binary dependencies that might not be available or reliable in all environments. This shift supports better integration with the broader ecosystem and allows for more predictable test environments.

**(c) strict grounded:**

> Not found in the provided PRs

## 2. Failure case: the grounded prompt fabricates a reason AND cites a chunk for it

**Question (nr10042, PR #10042):** Why were collectstatic's post-processing messages moved to verbosity level 2?

*PR #10042 changes a log level from 1 to 2; no reason is stated anywhere. The grounded answer claims the reason is 'reflected in the commit message' and cites PR10042-c0. Grounding instructions alone did not stop this (4 of 5 no-reason cases were not abstained).*

**(b) standard RAG:**

> The post-processing messages in `collectstatic` were moved to verbosity level 2 to reduce clutter in the default output, making it less verbose and more user-friendly for typical usage. This change ensures that only explicitly requested detailed output (at verbosity level 2) shows such messages, while lower verbosity levels (like 0 or 1) remain minimal and focused on essential actions. The adjustment aligns with Django's design principle of providing useful information without overwhelming users with intermediate or post-processing details.

**(c) strict grounded:**

> The post-processing messages were moved to verbosity level 2 to ensure they are only displayed when the user explicitly requests higher verbosity, improving the user experience by reducing clutter in default output. This change is reflected in the commit message and the code modification that sets the log level to 2 instead of 1 [PR10042-c0].

## 3. Without context the model even denies the premise; with the PR it answers correctly and cites the right chunk

**Question (q14349, PR #14349):** Why did URLValidator begin treating URLs with embedded line breaks or tab characters as valid on recent Python releases (3.9.5+)?

*Gold: Python 3.9.5+ urllib.parse silently strips ASCII newlines and tabs. URLValidator builds a punycode variant with urlsplit()/urlunsplit(), so the regex matched the cleaned URL and the original value with unsafe characters was treated as valid.*

**(a) no retrieval:**

> URLValidator did not begin treating URLs with embedded line breaks or tab characters as valid in Python 3.9.5 or any recent release. Python's URL validation behavior is not fundamentally changed in this version; such URLs are typically invalid by design because line breaks and tabs are not allowed in valid URL syntax. The perception of change may stem from improved error handling or more permissive parsing in certain contexts, but no official update to URLValidator in Python 3.9.5+ alters the validity of URLs containing line breaks or tabs.

**(c) strict grounded:**

> URLValidator began treating URLs with embedded line breaks or tab characters as valid on recent Python releases (3.9.5+) because Python's `urllib.parse()` automatically removes ASCII newlines and tabs from URLs, and the `URLValidator` uses `urllib.urlsplit()` and `urllib.urlunsplit()` to create a URL variant with Punycode, which no longer contains newlines and tabs in Python 3.9.5+. [PR14349-c0]
