Build an OpenClaw AgentSkill named Polaris.

Goal:
Create a local-first, modular skill that improves robustness, self-repair, learning capture, execution continuity, and fast rule iteration for long/complex tasks.

Hard constraints:
- Do NOT implement anything intended to bypass, evade, disable, or work around platform safeguards, system policies, prompt restrictions, approval boundaries, or security controls.
- Do NOT include self-preservation, replication, privilege escalation, or power-seeking behavior.
- Keep everything local-first, transparent, auditable, and easy to extend.
- Prefer free/open/local mechanisms only.

What Polaris SHOULD do:
- Modular architecture with replaceable components.
- Self-repair workflow for task failures (dependency/config/tool/runtime issues) via diagnosis -> local fix strategy -> retry guidance.
- Immediate progress reporting pattern with clear machine-readable state outputs.
- Capture lessons/heuristics/rules in a lightweight local memory/state format for future runs.
- Support fast short-task response and long-task continuity.
- Tool/adaptor registration pattern so new tools/APIs can be added with minimal friction.
- Rule iteration that is explicit, local, and reviewable.
- Work well with OpenClaw multi-agent/task flows without blocking them.
- Keep code concise and maintainable.

Desired deliverable in this temp repo:
- A complete AgentSkill folder named Polaris/
- SKILL.md
- Any supporting reference/docs/scripts/examples needed
- A concise README or reference notes if useful
- A clear architecture for: planner, repair engine, adapters, reporter, rule store, execution state
- Include examples of how Polaris would be used for long-chain local execution tasks
- Include explicit non-goals / safety boundaries

Important product direction:
- This is meant to outperform a simplistic self-improving loop by being more modular, faster, and less bottlenecked by slow feedback cycles.
- But it must achieve that by better architecture and local execution design, NOT by evading safeguards.

Output expectation:
- Create the skill files directly in this repo.
- When finished, provide a short summary of files created and key design decisions.

When completely finished, run this command to notify me:
openclaw system event --text "Done: Polaris skill scaffolded with modular repair/reporting architecture" --mode now
