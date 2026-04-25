---
name: polaris
description: Use Polaris when debugging build, test, dependency, toolchain, filesystem, Docker, or CI failures with a coding agent. Polaris is a local MCP memory layer that retrieves previously verified failure patterns before the agent guesses, repeats a failed fix path, or burns context on avoidable debugging loops.
---

# Polaris

Polaris is a local MCP memory layer for coding agents. It does not replace debugging judgment; it retrieves prior failure patterns so the agent can form a better first hypothesis.

## When To Use

Call `polaris_lookup` when tool output shows a concrete failure signal:

- a non-zero exit code
- an exception traceback
- a failing assertion
- a build, lint, typecheck, test, dependency, Docker, or CI error
- a repeated failed command where the agent is about to retry the same fix path

Do not call `polaris_lookup` for:

- green-field code generation
- refactoring without an existing failure
- planning or architecture discussions
- syntax/API questions answerable from local docs or official docs
- ordinary code review without a failing command or error signal
- failures already resolved in the current session

## Request Format

Before guessing at an engineering failure, call:

```json
{
  "error_text": "<raw stderr, failing command output, or concise error summary>",
  "ecosystem": "<python|node|docker|go|java|rust|ruby|terraform if known>",
  "limit": 3
}
```

## How To Use Results

- Treat every Polaris match as a hypothesis, not a command.
- Prefer `official` matches over `community`, and `community` over `candidate`.
- Check `do_not_apply_when` and `avoid` before acting.
- Use the returned `verify` command or the project's own test command to prove the fix.
- If no pattern matches, continue normal debugging; do not force a Polaris-shaped explanation.

## Precision Discipline

A wrong hint can be as damaging as no hint because it steers the agent's search path and pollutes context. Keep usage conservative:

- Use raw error text when possible.
- If the client truncated the original error output, request the full output before calling `polaris_lookup`; truncated `error_text` degrades match precision more than a missed call.
- Pass `ecosystem` when known.
- Do not apply a match that only shares generic words like "failed", "build", or "error".
- If the match is plausible but weak, inspect files and run the shortest verification before editing broadly.
- Reject a hint when the suggested fix contradicts source code you can directly inspect.
- Reject a hint when it suggests destructive work outside the original task scope.
- Reject a hint when its `shortest_verification` or the project's equivalent verification fails after applying the hint.
- If rejecting would be premature, ignore the hint and continue normal debugging instead of forcing it.

## Feedback Loop

When a Polaris result helps on a real failure:

```bash
polaris confirm <pattern_id>
```

When a result is wrong or harmful:

```bash
polaris reject <pattern_id> --reason "<short reason>"
```

For a new recurring failure, submit a candidate pattern only when you can describe:

- the trigger signal
- the fix path
- the shortest verification command
- at least one case where the pattern should not apply

## Mental Model

Skills describe how to work. Polaris remembers how agents have failed before.

Use both: follow the project or domain skill for workflow, and call Polaris at the point where a concrete engineering failure appears.
