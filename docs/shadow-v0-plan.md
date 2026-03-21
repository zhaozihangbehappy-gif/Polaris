# Shadow v0 Planning Baseline

## Status

This document formalizes the planning baseline that came out of the 2026-03-19 Shadow discussion with the OpenClaw-side workflow. It is not a completed product spec. It is the current convergence point that future specs should inherit unless explicitly revised.

## Source Context

Primary discussion artifacts:

- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/overview.md`
- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/merged-summary.md`
- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/brainstorming-context-verbatim.txt`
- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/claude-critical-feedback.md`
- `/home/administrator/.openclaw/workspace/context/shadow-2026-03-19/codex-critical-feedback.md`

## Product Frame

Shadow is currently framed as a consumer-grade full-body intelligent wearable direction, but it must not be treated as a single monolithic product.

The working decomposition is:

- `Shadow Helmet`: consumer smart helmet
- `Shadow Exo`: lightweight exoskeleton
- `Shadow Link`: helmet-to-exo coordination layer

This three-part split is the current planning boundary, not an optional naming exercise.

## Locked Planning Decisions

### 1. Modular but synergistic

The system must support both:

- independent value when sold separately
- extra value when used together

That means:

- Helmet must stand on its own
- Exo must stand on its own
- Link must add real coordination value instead of creating artificial dependency

### 2. First user anchor

The first user anchor is:

- enthusiast / geek personal augmentation

This is a scoping decision. It is not a claim that Shadow is a general-purpose platform at launch.

### 3. Primary value direction

The current value direction is:

- information enhancement
- safety / protection enhancement

The plan explicitly does not lead with exaggerated strength amplification.

### 4. Platform-level risk handling

Risk warning and avoidance cannot be defined as a helmet-only capability. It must be treated as a platform-level capability that can exist with or without the helmet, with richer behavior when coordinated.

### 5. Entry strategy

Current entry strategy:

- both Helmet and Exo may exist in the first release wave
- market emphasis is on Helmet
- Exo is lower-visibility and positioned more like a companion product

This is a go-to-market discipline, not an architecture change.

### 6. Price discipline

Current hard pricing pressure:

- Exo target: `2000-5000 RMB`
- Helmet launch price must stay close enough to ordinary non-smart helmets to compete for entry

The planning record treats "too expensive to sell" as a top-tier failure mode.

## What Not To Do

The discussion closed on several anti-patterns:

- do not write one giant spec for the whole Shadow vision
- do not let Helmet, Exo, Link deepen simultaneously without a scope gate
- do not treat broad ambition as proof of product definition
- do not keep expanding capability categories before a narrow first loop is proven

## Immediate Planning Consequences

The next planning stage should be constrained as follows:

1. Write a `Shadow v0` definition, or directly write a first `Shadow Helmet` spec.
2. Keep Exo and Link at interface-and-boundary level until Helmet scope is stable.
3. Force explicit statements for:
   - target user
   - first high-value scenario
   - non-goals
   - hard cost limits
   - safety and autonomy boundaries
4. Answer the product test:
   - why would a user buy the Helmet even without the Exo?

## Review Guidance

Any future proposal that violates one of these conditions should be treated as a scope change, not as a small iteration:

- it removes the Helmet / Exo / Link split
- it reverts to "general platform first"
- it makes dual-product launch deeper without narrowing the first scenario
- it ignores the price constraints
- it reintroduces strength amplification as the headline launch promise

## Current One-Line Summary

Shadow can still become large, but its next real step must be a tightly scoped beginning, not a full-vision spec.
