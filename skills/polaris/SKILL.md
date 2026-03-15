---
name: polaris
description: "Experience accumulation engine for agent tasks. Use when: (1) running a shell command that should benefit from prior failure avoidance, (2) orchestrating a local task with durable status and learning, (3) the user asks to 'run with Polaris' or 'use experience'. Polaris records failures, computes task fingerprints, and assembles avoidance hints so repeated runs avoid known-bad paths. NOT for: one-shot commands where learning is irrelevant, or tasks that need network/cloud execution."
metadata:
  {
    "openclaw": {
      "emoji": "🧭",
      "requires": { "allBins": ["python3", "bash"] }
    }
  }
---

# Polaris — Experience Accumulation Engine

Polaris wraps shell command execution with an experience loop: failures are classified, recorded with structured avoidance hints, and replayed on subsequent runs of the same task so the agent avoids known-bad paths.

## Quick Start

Run any shell command through Polaris:

```bash
POLARIS_RUNTIME_DIR="/tmp/polaris-run-$$" \
POLARIS_EXECUTION_KIND=shell_command \
POLARIS_MODE=short \
POLARIS_EXECUTION_PROFILE=standard \
POLARIS_SIMULATE_ERROR='' \
POLARIS_GOAL='<describe what the command does>' \
POLARIS_SHELL_COMMAND='<the actual command>' \
bash /home/administrator/.openclaw/workspace/projects/polaris-skill/Polaris/scripts/polaris_runtime_demo.sh
```

## When to Use Polaris

Use Polaris instead of raw `bash` when:

1. **The command might fail and you want to learn from it** — Polaris classifies failures (missing dependency, path issue, permission denial, etc.) and records structured avoidance hints.
2. **You'll run the same or similar command again** — On repeat runs, Polaris queries its failure store and applies avoidance hints (append flags, set env, rewrite cwd, set timeout) before execution.
3. **You want durable execution status** — Polaris writes structured state (`execution-state.json`) with adapter selection, contract planning, validation, and learning summaries.

Do NOT use Polaris for:
- Trivial one-shot commands (`echo`, `ls`, `pwd`) where learning overhead is pointless
- Commands that must run without any wrapper overhead
- Network/cloud tasks (Polaris is local-exec only in current phase)

## How It Works

### Experience Loop (L2 Path Pruning)

1. **Task Fingerprint** — Each command + cwd is fingerprinted (SHA-256 normalized key). Same logical task = same fingerprint across runs.
2. **Failure Store Query** — Before execution, Polaris queries `failure-records.json` for prior failures matching this fingerprint.
3. **Avoidance Hints Assembly** — Matching failures produce structured hints from 4 restricted primitives:
   - `append_flags` — add CLI flags to the command
   - `set_env` — set environment variables
   - `rewrite_cwd` — change working directory
   - `set_timeout` — adjust timeout
4. **Hint Application** — The shell-command adapter applies hints before execution. Conflict rule: `avoid` hints always win over `prefer` hints of the same kind.
5. **Failure Recording** — If execution fails, the failure is classified and a new record with avoidance hints is written to the store.

### Execution Flow

```
bootstrap → adapter selection → contract planning → experience hints assembly
  → shell execution (with applied hints) → validation → failure recording (if failed)
  → repair classification → learning consolidation
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `POLARIS_RUNTIME_DIR` | `Polaris/runtime-demo` | Directory for all runtime artifacts |
| `POLARIS_EXECUTION_KIND` | `auto` | `auto`, `runner`, `shell_command`, `file_analysis`, `file_transform` |
| `POLARIS_EXECUTION_PROFILE` | `deep` | `micro`, `standard`, `deep` |
| `POLARIS_MODE` | `long` | `short`, `long` |
| `POLARIS_GOAL` | (required) | Human-readable goal description |
| `POLARIS_SHELL_COMMAND` | (empty) | The shell command to execute (required for `shell_command` kind) |
| `POLARIS_SHELL_CWD` | (runtime dir) | Working directory for the command |
| `POLARIS_SHELL_TIMEOUT_MS` | `60000` | Command timeout in milliseconds |
| `POLARIS_SIMULATE_ERROR` | (empty) | Set empty string for real execution |
| `POLARIS_RESUME` | (empty) | Set non-empty to resume a blocked run |

## Runtime Artifacts

After a run, `POLARIS_RUNTIME_DIR` contains:

- `execution-state.json` — Full orchestration state (status, artifacts, learning summary)
- `runtime-execution-result.json` — Shell command output (stdout, stderr, exit code, duration)
- `failure-records.json` — Accumulated failure experience store
- `success-patterns.json` — Success pattern store for learning consolidation
- `adapters.json` / `rules.json` — Bootstrapped adapter registry and rules

## Interpreting Results

Check the execution state:

```bash
python3 -c "import json; s=json.load(open('$POLARIS_RUNTIME_DIR/execution-state.json')); print(s['status'], s.get('summary_outcome',''))"
```

- `completed` — command succeeded, learning captured
- `blocked` — command failed, failure recorded, repair attempted

Check if experience was applied:

```bash
python3 -c "import json; r=json.load(open('$POLARIS_RUNTIME_DIR/runtime-execution-result.json')); print('applied:', r.get('experience_applied', []))"
```

## Scripts Reference

All scripts are in the project directory at:
`/home/administrator/.openclaw/workspace/projects/polaris-skill/Polaris/scripts/`

| Script | Purpose |
|---|---|
| `polaris_runtime_demo.sh` | Entry point — sets up env and calls orchestrator |
| `polaris_orchestrator.py` | Main orchestration engine |
| `polaris_adapter_shell.py` | Real shell command execution with hint application |
| `polaris_task_fingerprint.py` | Task fingerprint computation and matching |
| `polaris_failure_records.py` | Failure experience store (record, query, build hints) |
| `polaris_bootstrap.py` | Bootstrap adapters, rules, patterns from manifest |
| `polaris_contract_planner.py` | Execution family selection |
| `polaris_validator.py` | Contract validation |
| `polaris_repair.py` | Failure classification and repair planning |
| `polaris_regression.sh` | Full regression suite (Platform-0 + Phase 1) |
