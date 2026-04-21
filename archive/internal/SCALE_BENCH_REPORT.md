# Scale Benchmark Report (v4)

Generated: 2026-04-20
Source: `scale-bench-report-v4.json`
Script: `eval/bench_scale.py`

## Runtime SLA verdict

| Mode | Overall pass | p95 latency cap (10ms) | token cap | token mult cap (1.2×) | latency mult cap (1.2×) |
|---|---|---|---|---|---|
| full | FAIL | ✅ at all pools | ✅ at all pools | ❌ at ≥500 | ✅ at all pools |
| constant_budget (runtime default) | **PASS** | ✅ | ✅ | ✅ | ✅ |

## constant_budget — per-pool numbers

All gates pass for every pool.

| Pool | p95 ms | tok_max | token_mult | latency_mult |
|---:|---:|---:|---:|---:|
| 167 | 0.0094 | 100 | 1.000 | 1.000 |
| 300 | 0.0109 | 100 | 1.000 | 1.000 |
| 500 | 0.0145 | 100 | 0.954 | 1.000 |
| 697 | 0.0161 | 100 | 0.931 | 1.000 |
| 1000 | 0.0221 | 100 | 0.931 | 1.000 |
| 1500 | 0.0261 | 98 | 1.000 | 1.000 |

Caps: p95 ≤ 10 ms · tokens ≤ 100 · token_mult ≤ 1.2× · latency_mult ≤ 1.2×
(baseline = pool 167, latency_mult uses 0.1ms operational floor).

## full — per-pool numbers

| Pool | p95 ms | tok_max | token_mult | latency_mult | pass? |
|---:|---:|---:|---:|---:|---|
| 167 | 0.0098 | 193 | 1.000 | 1.000 | ✅ |
| 300 | 0.0129 | 193 | 1.066 | 1.000 | ✅ |
| 500 | 0.0185 | 234 | 1.396 | 1.000 | ❌ token_mult |
| 697 | 0.0219 | 234 | 1.560 | 1.000 | ❌ token_mult |
| 1000 | 0.0275 | 291 | 2.308 | 1.000 | ❌ token_mult |
| 1500 | 0.0386 | 293 | 2.484 | 1.000 | ❌ token_mult |

Full mode returns top-3 matches uncapped; once the pool has more cousin-
patterns the secondary matches drag injected tokens up past the 1.2×
baseline envelope. Latency alone never threatens the cap — the pool index
scales sub-linearly.

## Runtime default

`adapters/mcp_polaris/polaris_index.py` sets `CONSTANT_CONTEXT_TOKEN_BUDGET
= 100`. At runtime the Polaris MCP server emits at most one top pattern
and truncates the payload to that budget. This is the mode that an agent
sees in production.

## Quality tradeoff

`constant_budget` returns at most one matching pattern. Queries that match
multiple patterns (e.g. a stderr fragment shared by three cousin classes)
lose the secondary signal. That is an intentional tradeoff: the contract
the SLA gates protect is *latency × token_mult within 1.2× of pool 167
baseline*, and full-mode cannot hold that envelope past pool 300.

## What this means for launch

Even at **1500 patterns** (> 2× the current schema-valid pool of 697 and
1.5× the 1000-pattern target), the runtime path:

- uses at most ~100 injected tokens of context budget
- p95 match latency stays at 0.026 ms — three orders of magnitude under
  the 10 ms cap
- agent round-trip sees a constant-size payload regardless of catalog growth

Runtime-SLA blockers to shipping: **none**. Pool-size growth is not a
latency or token blocker. The remaining gating concern is pattern-level
`verified_live` count (see VERIFIED_PROMOTION_REPORT.md), which is an
offline audit question, not a runtime one.
