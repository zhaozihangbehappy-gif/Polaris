# Roadmap

## Evaluation

Polaris needs pattern-level safety metrics, not only end-to-end success metrics.

Current eval focuses on task-level outcomes such as CI pass, rounds to root cause,
tool calls, and human intervention. That is useful, but it does not fully measure
the cost of a bad hint.

Next evaluation work:

- Add hint-quality trials: same failure task with no Polaris hint, correct Polaris
  hint, and deliberately wrong hint.
- Track whether wrong hints increase rounds to root cause versus no hint.
- Generate wrong hints with adversarial variants, not only hand-written cases:
  - wrong root cause with the same visible error shape
  - right root cause with the wrong concrete fix
  - unrelated pattern from another ecosystem or error class
- Add per-pattern positive fixtures that should match.
- Add per-pattern negative fixtures that look similar but must not match.
- Report pattern-level true positives and false positives alongside end-to-end
  success rate.

## Pattern Promotion

Community votes are useful, but votes alone should not promote a pattern into the
official tier.

Promotion path:

1. `candidate`: shape-valid, surfaced with a visible tier label.
2. `community`: at least two independent confirmations and zero rejects.
3. `official-candidate`: someone submits a complete fixture set for the
   community pattern.
4. `official`: automated regression passes plus maintainer review.

A complete fixture set means:

- at least one positive fixture that should trigger the pattern
- at least one negative fixture that looks similar but must not trigger
- a shortest verification command or equivalent proof path

Fixture submission is the promotion action from `community` to
`official-candidate`; it is not maintainer cleanup after the fact.

New contributed patterns should include at least one negative fixture. This
forces contributors to state where the pattern should not trigger, which is the
main defense against harmful false positives.
