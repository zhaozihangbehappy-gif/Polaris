# Usage Patterns

## Long-Chain Local Execution

1. Initialize state:
   `python3 Polaris/scripts/polaris_state.py init --state run.json --goal "Upgrade Polaris" --mode long --execution-profile deep --active-layers hard,soft`
2. Build the plan:
   `python3 Polaris/scripts/polaris_planner.py --state run.json --goal "Upgrade Polaris" --mode long --execution-profile deep`
3. Register or inspect adapters:
   `python3 Polaris/scripts/polaris_adapters.py select --registry adapters.json --capabilities local-exec,validation --mode long --execution-profile deep --max-trust workspace --max-cost 5 --sticky-cache adapter-selection-cache.json`
4. Select a reusable success pattern:
   `python3 Polaris/scripts/polaris_success_patterns.py select --patterns success-patterns.json --tags orchestration,local --mode long --min-confidence 60`
5. Diagnose a failure:
   `python3 Polaris/scripts/polaris_repair.py diagnose --error "ModuleNotFoundError: No module named yaml" --execution-profile standard --attempt-count 1`
6. Capture a layered rule:
   `python3 Polaris/scripts/polaris_rules.py add --rules rules.json --rule-id validate-before-finish --layer soft --trigger "task appears complete" --action "run local validation before final notification" --evidence "caught malformed output locally" --scope "local skill work" --tags validation,local`
7. Capture a success pattern:
   `python3 Polaris/scripts/polaris_success_patterns.py capture --patterns success-patterns.json --pattern-id local-verify-loop --summary "Local verify before notify" --trigger "skill edits are complete" --sequence plan,execute,validate,notify --outcome "clean finish with auditable evidence" --evidence run.json --tags local,validation --confidence 75 --lifecycle-state validated`

## Resume Pattern

- Read the state file first.
- Inspect the latest event snapshot and event log.
- Resume from `state_machine.node`, `state_machine.active_branch`, and `next_action`.
- If the node is `repairing`, read the repair report, repair plan, and recovery references before retrying.

## Fast Local Pattern

- Use `--execution-profile micro --mode short` for bounded one-shot tasks.
- Use `--execution-profile standard --mode short` for short tasks that still benefit from an explicit adapter choice, validation phase, and shallow-first repair routing.
- Use `--execution-profile deep --mode long` when repair, resumability, or rich surfaces are important.

## Iteration Pattern

- Start with `hard,soft`.
- Add `experimental` only for narrow candidate improvements.
- Promote or delete experimental guidance based on observed local outcomes.
