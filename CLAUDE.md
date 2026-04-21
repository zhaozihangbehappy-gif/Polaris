# Polaris — agent instructions

## Archive Boundary

Unless the user explicitly instructs otherwise, agents must not read files under `archive/`, must not cite `archive/` as the default source of truth, and must not create, modify, or append files under `archive/`. `archive/` is a frozen historical evidence library. It is public for transparency, but it is not part of the active product surface, release workflow, or default working set.

## Default working set

- `README.md`
- `START_HERE.md`
- `FACTS.md`
- `INSTALL.md`
- `SKILL.md`
- `CLAUDE.md`

Anything outside this set is not product surface. Do not treat it as spec.
