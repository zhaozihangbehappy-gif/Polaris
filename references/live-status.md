# Live Status Pattern

Polaris should keep progress legible without asking for repeated authorization.

## Recommended fields

- `run_id`
- `status`
- `progress_pct`
- `current_step`
- `summary`
- `next_action`

## Recommended outputs

- append-only JSONL event log
- current status snapshot file
- repair report file when a retry branch is triggered

## Why this matters

This gives orchestration and humans one stable place to inspect current work without reconstructing context from scattered messages.
