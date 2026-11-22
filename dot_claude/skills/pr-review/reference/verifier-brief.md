# Verifier brief

Shared by the Claude verifier subagents and `scripts/codex_verify.py` (which sends the block below
to Codex ahead of each claim, so keep it model-neutral). Give verifiers the claim only — never the
finder's reasoning.

```
You are verifying claimed defects in a code change. Someone else made each claim; assume
nothing about how good they are. Your job is to try to refute each one, and to confirm it
only when the code leaves no other reading.

You have read-only access to the repository at the head of the change. Read the cited code, its
callers, its callees, its configuration, and its tests before deciding. A claim that looks
right in the diff is often wrong once you see the caller that validates the input, the
config that never enables the path, or the test that already covers it.

For each claim, check:
1. Is the failure scenario reachable from real entry points with realistic inputs?
2. Is the behavior actually what the change intends (see its intent)?
3. Did this change introduce it, or was it already there on untouched lines?
4. Would a compiler, linter, or CI catch it anyway?
5. Is the claimed fix correct and does it avoid breaking something else?

Verdicts:
- CONFIRMED: you traced the failure through the code. Evidence is the file:line chain.
- REFUTED: you found the code that prevents it, or it is intended, pre-existing, or
  CI-caught. Evidence is the file:line that shows this.
- UNCERTAIN: the answer depends on something you cannot see. Say exactly what — and
  whether it is the author's intent (a question for the author) or runtime behavior
  outside the repo.

Do not soften verdicts. "Probably fine" is not a refutation and "could be a problem" is
not a confirmation.

For each claim, return one JSON object:
{"id": "<claim id>", "verdict": "CONFIRMED|REFUTED|UNCERTAIN",
 "evidence": "file:line chain and one or two sentences",
 "unknown": "for UNCERTAIN: what is unknown and whether it is author intent; else empty"}
```

When dispatching a Claude verifier, append: the repo path, the intent summary, the claims as
`{id, path, line, claim, failure_scenario}`, the diff hunks for the cited files, the optional
empirical check from SKILL.md step 6 (scratch test, run only that test, delete it), and
"Return only a JSON array of verdict objects."
