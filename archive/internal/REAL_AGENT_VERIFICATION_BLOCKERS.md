# Real-Agent Verification Blockers

Generated: 2026-04-19

## CLI status on this machine

| Tool | Status |
|---|---|
| codex | `/home/administrator/.local/bin/codex` v0.121.0 |
| claude | `/home/administrator/.local/bin/claude` v2.1.114 |
| cursor | `/mnt/d/program/cursor/resources/app/bin/cursor` v2.6.18 |

Codex and Claude CLIs are installed. Cursor still requires manual transcript
export unless a stable headless runner is added.

## Current state

Verified count is **4** after Codex successfully completed four hermetic cases.
The previous 8 contaminated evidence rows remain invalidated and do not count.

The harness has been changed so future runs use hermetic per-variant workdirs
and require `pre_failure_reproduced=true`.

## Current blockers

1. Claude Code hit the five-hour account limit during the same four-case batch:
   `You've hit your limit · resets 11pm (Asia/Shanghai)`.
2. Cursor has no headless agent runner in this harness. It requires manual
   transcript files under `eval/runs/manual_cursor/`.
3. 691 generated skeletons still need real fixtures or issue snapshots before
   they can be promoted.
4. Real issue share is still 0%, so launch verdict stays blocked.

## Remaining work before cross-agent verified growth

1. Re-run the same four cases with Claude after the rate-limit reset.
2. Produce Cursor baseline/polaris transcript artifacts or implement a stable
   Cursor runner.
3. Keep only results where `expected_failure_command` fails before the agent and
   `fix_command_test` passes after the agent.
4. Author real fixtures for the 691 generated skeletons currently blocked by
   `blocked_no_fixture`.
5. Add real GitHub issue cases; current real-case share is still 0%.

## What is not acceptable

- Counting candidate records as verified.
- Counting old contaminated artifacts as verified.
- Counting a run where the post-test passes because the test command itself
  bakes in the fix.
- Counting mock runner output.
