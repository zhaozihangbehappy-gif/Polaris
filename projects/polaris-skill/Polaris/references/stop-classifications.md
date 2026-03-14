# Runtime Stop Classifications

This file documents the stop classifications Polaris preserves at runtime.
It is not a general platform-policy reference.

## Stop Types

- `approval_denial`: the action was denied by an approval gate
- `permission_denial`: the environment does not provide required access
- `execution_envelope_denial`: execution cannot cross the current runtime envelope
- `nonlocal_denial`: the requested change would leave the local/workspace contract
- `nonverifiable_result`: the result cannot be validated from local evidence

## Runtime Meaning

When a failure lands in one of these classes:

- classify it as `nonrepair_stop`
- do not route it into repair learning
- do not promote rules or success patterns from it
- set `status=blocked`
- produce a `next_action` that changes the request, scope, or environment
- keep the denial evidence in state/artifacts for audit

## Repairable Contrast

Failures may still route into repair when they stay local and verifiable, for example:

- dependency visibility or interpreter mismatch
- missing tool or PATH resolution issues
- import-path / config / workdir mistakes
- path or missing-file mistakes
- bounded local test failures

## Operator Guidance Rule

- stop classification -> adjust request, scope, or environment
- repairable failure -> allow retry, fallback, or deeper repair routing
