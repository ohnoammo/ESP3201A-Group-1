# rm12342: redacted PR #12342 (answer removed, PR kept) - all non-diff parts

Removed: comment 576236632 by @matthijskooijman (the answer) and the description sentence "If a third database is added, accessing it is prevented by the test environment, resulting in a failing testcase." Diff hunks are unchanged and omitted below.

## [title_description]
Title: Refs #31117 -- Made various tests properly handle unexpected databases aliases.

Description:
Quite some test in the testsuite assumed that the test configuration
only contains a 'default' and 'other' database, for no good reason. This
commit removes these assumptions.

This commit was originally written to allow a third database to be used
for testing database creation, but that turned out to be infeasible for
other reasons (see https://github.com/django/django/pull/12247). Still,
cleaning up these assumptions makes the code slightly cleaner and makes it easier to add an additional database in the future.

The fixed assumptions are as follows.
 - In most cases, a testcase would use the `databases = [...]` to
   declare it used 'default' and 'other', but then access all databases
   through `django.db.connections`. This is easy to fix by simply iterating over the
   `databases` value rather than `django.db.connections`.
 - `backends.tests` would hardcode the number of connections to 2, now
    it uses `len(connections)` instead.
 - `migrations` had some database routers that assumed only two
   databases. These were slightly changed to keep equivalent behaviour,
   without trying to migrate anything other than 'default' and 'other'.
 - `test_runner.test_discover_runner` would make assumptions about skip
   messages that were not necessarily true. These were adapted by
   autogenerating any skipped connections.


## [commits]
Commit messages:
Refs #31117 -- Made various tests properly handle unexpected databases aliases.

- Used selected "databases" instead of django.db.connections.
- Made routers in tests.migrations skip migrations on unexpected
  databases.
- Added DiscoverRunnerGetDatabasesTests.assertSkippedDatabases() hook
  which properly asserts messages about skipped databases.


## [conversation]
Comment by @felixxm:
@matthijskooijman Thanks :+1: I'm not sure about changing `django.db.connections` to `databases`, because we don't support creating databases at runtime, and moreover this may hide isolation issues.


## [conversation]
Comment by @matthijskooijman:
> I'm not sure about changing django.db.connections to databases, because we don't support creating databases at runtime, and moreover this may hide isolation issues.

Do you mean changes like these?

```
-        for db in connections:
+        for db in self.databases:
```

If so, I think they should be equivalent, since iterating over `django.db.connections` results in iteration over db alias names, and `self.databases` is just a list of alias names?

Or am I misunderstanding your meaning?


## [conversation]
Comment by @felixxm:
> If so, I think they should be equivalent, since iterating over `django.db.connections` results in iteration over db alias names, and `self.databases` is just a list of alias names?

They are not the same, `cls.databases` is a subset on connections (see [documentation](https://docs.djangoproject.com/en/3.0/topics/testing/tools/#django.test.TestCase.databases)). I agree that we can use `cls.databases` to remove assumption that `connections` contains only `default` and `other`. Let me double-check proposed changes.


## [conversation]
Comment by @felixxm:
@matthijskooijman Thanks for this patch :+1: I pushed small edits and added `DiscoverRunnerGetDatabasesTests.assertSkippedDatabases()` to simplify tests.


## [conversation]
Comment by @matthijskooijman:
Looks good!


## [conversation]
Comment by @matthijskooijman:
I see you changed the skip message matching to use a set and then sorting the result, but I was under the impression that the order of databases in the skip message is not sorted, but ordered in the same order as databases are specified in the connections dict?


## [conversation]
Comment by @felixxm:
I added sorting because we [sort aliases of unused databases](https://github.com/django/django/blob/26be703fe679a58bbdccf37a276a9c430ccb29f7/django/test/runner.py#L677).


## [conversation]
Comment by @matthijskooijman:
Ah, then I misremembered. Looks good, then, thanks for clarifying :-)

