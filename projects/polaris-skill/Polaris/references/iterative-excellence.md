# Iterative Excellence

Polaris should improve by tightening local evidence loops, not by becoming more autonomous or less visible.

## Improvement Priorities

- remove avoidable manual coordination
- reduce repeated failures with narrow reusable rules
- capture successful execution sequences that are likely to recur
- productize the lifecycle of rules and patterns without hiding why they changed

## Improvement Cycle

1. run with `hard` and `soft` guidance first
2. add `experimental` guidance only for a specific recurring problem
3. validate locally
4. capture a success pattern with confidence and expiry when the sequence worked
5. promote, demote, retire, or expire guidance based on evidence

## Lifecycle Concepts

- rules: promote only when local evidence justifies it; demote or delete stale heuristics
- patterns: track `experimental`, `validated`, `preferred`, `retired`, and `expired`
- both: keep confidence explicit and easy to audit

## Quality Bar

- concise enough to read quickly
- explicit enough to resume without guesswork
- precise enough that explicit stop classifications are never framed as repair targets
- modular enough that adapters, rules, and patterns can evolve independently
