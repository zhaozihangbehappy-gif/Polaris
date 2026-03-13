# Polaris vs self-improving-agent — Source-Level Comparison (2026-03-13)

## Scope

This comparison is based on downloaded source files, not registry descriptions alone.

### Compared sources

#### Polaris
Imported from temporary work under:
- `projects/polaris-skill/Polaris/`

Key files inspected:
- `Polaris/SKILL.md`
- `scripts/polaris_state.py`
- `scripts/polaris_orchestrator.py`
- `scripts/polaris_adapters.py`
- `scripts/polaris_repair.py`
- `scripts/polaris_repair_actions.py`
- `scripts/polaris_runtime.py`
- `scripts/polaris_success_patterns.py`

#### self-improving-agent
Downloaded without installing into a live skill path and inspected from a temporary source snapshot.

Key files inspected:
- `SKILL.md`
- `scripts/activator.sh`
- `scripts/error-detector.sh`
- `scripts/extract-skill.sh`
- `hooks/openclaw/handler.ts`
- `references/openclaw-integration.md`
- `references/examples.md`

## High-level conclusion

The two skills operate at different architectural layers.

### self-improving-agent
Best understood as a:
- learning capture system
- correction/error log system
- promotion pipeline into long-term memory / prompt files
- lightweight skill-extraction helper

### Polaris
Best understood as a:
- local-first execution runtime
- explicit orchestration system
- state-machine-driven task runner
- bounded repair and adapter-selection framework
- success-pattern learning system tied to execution outcomes

## Core difference

### self-improving-agent optimizes for
"remember this and avoid repeating the mistake"

### Polaris optimizes for
"execute this complex local task in a structured, resumable, repairable, and increasingly reusable way"

## Concrete strengths

### self-improving-agent strengths
- extremely lightweight
- easy to understand and deploy
- strong for immediate capture of:
  - user corrections
  - command failures
  - missing capabilities
  - best practices
- useful promotion path into:
  - `AGENTS.md`
  - `SOUL.md`
  - `TOOLS.md`
  - `CLAUDE.md`
- practical helper for extracting recurring learnings into new skills

### Polaris strengths
- much stronger execution architecture
- explicit plan/state/runtime surfaces
- layered rules (`hard` / `soft` / `experimental`)
- structured adapter registry and selection
- bounded local repair planning
- success-pattern capture with confidence/lifecycle semantics
- resumable orchestration instead of pure note-taking
- profile-aware agility (`micro` / `standard` / `deep`)
- sticky adapter reuse and repair-depth escalation after Phase 2

## Weakness comparison

### self-improving-agent weaknesses
- not an execution runtime
- no explicit state machine
- no adapter ranking system
- no repair tree
- no durable runtime surface
- learning is largely markdown-entry based and weakly structured compared with Polaris
- easy to accumulate logs faster than execution quality improves

### Polaris weaknesses
- heavier than a pure learning logger
- more moving parts to maintain
- over-activation risk if profiles and budgets are ignored
- remaining Phase 3 work still needed so learning growth stays off the foreground hot path

## Deployment effect comparison

### If deployed alone: self-improving-agent
Likely effect:
- better memory of past mistakes and corrections
- better capture of recurring project conventions
- low-friction accumulation of learnings

But it would not by itself materially improve:
- long-chain orchestration quality
- resumability
- adapter/tool-routing quality
- bounded repair behavior

### If deployed alone: Polaris
Likely effect:
- stronger execution structure on complex local tasks
- better failure handling and recovery shape
- better resumability and runtime observability
- better reuse of successful execution patterns

This makes Polaris the better foundation for a high-spec growth-oriented agent runtime.

## Best synthesis direction

Do not collapse Polaris into a markdown-log-only skill.

Instead:
- keep Polaris as the execution/evolution runtime
- selectively absorb the best low-friction learning-capture ideas from self-improving-agent
- especially for:
  - cheap learning markers
  - promotion pathways
  - easier extraction of recurring patterns into reusable skills

## Practical result of today’s comparison

The comparison confirmed that:
- self-improving-agent is genuinely useful
- but it is not the stronger candidate for the desired “highest-spec growth-form” runtime
- Polaris is the stronger execution substrate
- the best future direction is additive absorption, not replacement
