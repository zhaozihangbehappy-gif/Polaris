# Facts

Polaris is a memory layer for AI coding agents. That's the whole product.

Polaris was built against recurring engineering failure, not demo-friendly prompts.

## What's in it

- 167 failure patterns
- 8 language ecosystems
- Open source (AGPL-3.0-only)
- Runs locally as an MCP tool

## What the numbers mean

- 167 patterns: distinct recurring failures with a known fix shape. Not rules. Not prompts.
- 8 ecosystems: the stacks most agents trip on in real work.
- 66.2% holdout: accuracy on unseen failure samples during internal evaluation.
- 44/44 gates: internal release checks. Historical. Not a promise about your repo.

## How it grows

Polaris has a community channel. Users can submit new candidate patterns and confirm or reject existing candidates. A candidate enters the community-verified tier after at least 2 independent users confirm it helped them on real cases, with zero rejects. The shared library Polaris loads is three-tiered: `official` (internal verified-live — the 167), `community` (community-verified through this channel), and `candidate` (unconfirmed but available to try). Each lookup result carries its tier. This is how Polaris grows — not just from a central team, from the people who use it.

In this release, the shipped `candidate` tier spans all 8 ecosystems. The `official` tier remains the broad audited library, while candidates trade certainty for wider coverage.

## What it is not

- Not a coding agent.
- Not a replacement for your model.
- Not a guarantee your build will go green.
- Not license-gated. The paid link is support.

## Older material

Audit reports, release gates, and evaluation logs live under `archive/` and `eval/`. Public, frozen, not part of the product.
