# Polaris v1 Integration Checklist

**Purpose**: wire real Cursor / Claude Code / Codex into the Gate 2 harness. Everything here runs on **your subscribed machine**, not this sandbox.

**Pre-flight verdict rule (NARRATIVE.md §4)**: if the final `launch_verdict.status != "pass"`, nothing from this run can be used externally. Period.

---

## 0. Machine readiness

```bash
codex --version          # Codex CLI, Pro plan logged in
claude --version         # Claude Code CLI, Pro plan logged in
cursor --version         # Cursor installed; auto-mode subscription active
python3 --version        # >= 3.10
pnpm --version           # >= 9.0  (for case_002)
docker --version         # >= 24.0 (for case_003)
```

If any is missing, stop here and install. Do **not** proceed with a partial set — 木桶.

## 1. Fixture build + validate

```bash
cd /path/to/Polaris
python3 -m eval.fixtures_manifest build        # writes manifest.json per case
python3 -m eval.fixtures_manifest validate     # rehashes; expect all "ok"
```

Then stage each case into `/tmp`:

```bash
for case in case_001_python_pythonpath case_002_node_enoent_lockfile case_003_docker_layer_cache; do
  cd eval/fixtures/$case
  bash -c "$(jq -r '.build_commands | join(\"\\n\")' manifest.json)"
  cd -
done
```

## 2. Reproduce the failure (sanity)

For each case, run its `expected_failure_command` and confirm stderr matches `expected_failure_stderr_regex`. If it doesn't fail as expected, the fixture is broken — do not proceed.

```bash
jq -r '.expected_failure_command' eval/fixtures/case_001_python_pythonpath/manifest.json | bash 2>&1 | grep -E "$(jq -r '.expected_failure_stderr_regex' eval/fixtures/case_001_python_pythonpath/manifest.json)"
```

## 3. Implement three runners (木桶 equal)

Edit in parallel, land together:

- `eval/runners/codex_runner.py` — subprocess `codex exec --session-log <path> "<prompt>"`
- `eval/runners/claude_code_runner.py` — subprocess `claude -p "<prompt>" --output-format stream-json`
- `eval/runners/cursor_runner.py` — load an exported transcript file

**Parsing contract (same for all three)**:
- `rounds_to_root_cause`: first assistant turn where response matches `success_criteria.root_cause_regex`; `None` if never
- `redundant_actions_count`: count of tool calls whose (tool_name, stringified_args) exactly matches a previous one
- `token_consumption`: sum of reported input+output token usage
- `tool_calls`: total tool_use blocks
- `ci_pass`: exit code of running `success_criteria.fix_command_test` after the session
- `human_intervention_count`: count of user messages injected after the initial prompt (for automated runs: 0)

**Do not fabricate any metric.** Return `None` rather than guessing.

## 4. Rate-limit budget

- Claude Code Pro: 9 cases × 3 sessions × ≤10 rounds ≈ 300 messages. Stay under daily cap by running in batches of 3 cases/day.
- Codex Pro: similar, no hard schedule; monitor.
- Cursor: auto-mode has its own fast-tier usage; manual transcript path bypasses limits.

If a rate limit fires mid-run, the runner should write a partial transcript with `status: "rate_limited"` and let orchestrator record the error — do **not** silently retry.

## 5. First real run

```bash
python3 -m eval.orchestrator --runner codex,claude_code,cursor --seed 20260419
```

Expected: 18 runs (3 runners × 3 cases × 2 variants). Results under `eval/runs/<ts>/`.

Inspect summary:

```bash
jq '.launch_verdict, .hard_gate_passing_pairs, .hard_gate_total_pairs' eval/runs/<ts>/summary.json
```

## 6. Evidence writer (TODO for v1)

A script you'll want before Gate 3:

- Input: `eval/runs/<ts>/results.json`
- For each `verified_live`-eligible result (fix_command_test passed), compute `sha256` of transcript, and append an `AgentReproEvidence` into the matching pattern's `agent_reproducibility.evidence` in `experience-packs-v4/`.
- Re-run `scripts/pattern_validator_v4.py` — `counts_toward_1000_target` should become > 0 for the first time.

I have **not** written this yet. When you're ready, ping me with the first real run's results and I'll scaffold it.

## 7. What you should ask me to write next (optional, order by ROI)

1. Real-issue case curator — scrape 2-3 GitHub issues matching NARRATIVE.md疼点迁移 (monorepo / CI-only / long-session repeat-mistakes) and emit cases at the same JSON contract. Needed to lift `real_case_share` from 0% toward the ≥30% v0 floor.
2. `evidence_writer.py` — see §6.
3. MCP server scaffold (`adapters/mcp-polaris/`) — required for `polaris_enabled=True` runs to actually inject patterns into Cursor/Claude Code/Codex. Without this, "with_polaris" is just the same baseline re-run.

**Important**: item 3 is the real v1 blocker. A `with_polaris` run without the MCP adapter is not a `with_polaris` run — it's a duplicate baseline. I flagged this now so you don't discover it on run day.

---

## My role

I can't run any of the above from this sandbox. You run steps 0-5. When results come back, paste `eval/runs/<ts>/summary.json` and I'll write the evidence writer + diagnose any runner integration issues.

If you'd rather I continue writing here instead of you running, tell me which of §7's items to do next — I'll keep the scaffolding gate-compliant.
