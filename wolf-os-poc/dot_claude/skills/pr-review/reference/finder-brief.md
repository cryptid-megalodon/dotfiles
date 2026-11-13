# Finder brief

Fill the `{}` slots and send as the subagent prompt. Keep one finder to one lens.

```
You are reviewing part of a pull request in WhoopInc/{repo} (PR #{n}, head {sha}).
The full repo at that head is checked out read-only at {worktree}. Read surrounding code,
callers, and tests there whenever a judgment depends on them. Do not edit anything.

## What the PR is for
{intent summary}

## Already raised on the PR (do not repeat)
{already-raised list, or "none"}

## Your lens
{one of:}
- CORRECTNESS: find changes that make the code behave wrongly — wrong results, crashes,
  data loss, broken edge cases (empty, null, boundary, concurrent, retry, partial failure),
  security holes, and breakage the change causes in its callers. Check performance
  regressions explicitly (N+1 calls, repeated scans, unbounded memory, work moved into a
  hot path); reviewers routinely miss them. Ignore style. {Python: also apply the checklist
  at {PY_RULES}/logic/SKILL.md.}
- CONVENTIONS: check the diff against these rule files, and only these. Read each first:
  {absolute paths of routed rule files, severity.md, false-positives.md, repo CLAUDE.md
  files, suppressions.md}
  A finding must cite the rule it violates by name. {Java contract check, if applicable:
  run the org-wide consumer search in {JAVA_RULES}/SKILL.md step 4 and name consumers.}

## The diff to review
{chunk diff — for CONVENTIONS, the full reviewable diff}
Other files changed in this PR (for context only): {file list}

## What to return
Aim for recall: report every candidate you believe is real; a separate verifier will try to
refute each one. But every candidate must name a concrete failure — specific inputs or state
leading to a specific wrong outcome ("a request with an empty `ids` list reaches
`ids.get(0)` at FooService.java:88 and throws, returning 500"). If you can't name one, it's
not a candidate. Skip lines the PR didn't touch unless the PR causes the breakage there, and
skip anything a compiler, linter, Spotless, or CI would catch.

Return only a JSON array, no prose:
[{"path": "...", "line": 123, "claim": "one sentence: what is wrong",
  "failure_scenario": "inputs/state -> wrong outcome, with file:line evidence",
  "rule": "rule name or null", "severity": "Blocking|Should fix|Nit|Question"}]
Return [] if nothing survives your own scrutiny.
```
