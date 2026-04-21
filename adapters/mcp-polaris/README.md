# polaris-mcp adapter

Stdio MCP server exposing `polaris_lookup`.

## Install

```bash
pip install -r adapters/mcp-polaris/requirements.txt
```

## Standalone smoke-test (no agent)

```bash
python3 -c "
from adapters.mcp_polaris.polaris_index import match, format_for_injection
hits = match(\"ModuleNotFoundError: No module named 'mymod'\", ecosystem='python')
print(format_for_injection(hits))
"
```

Expected: a JSON payload with `patterns: [...]` and `_budget.used_tokens_est ≤ 300`.

## Register with agents

### Claude Code

```json
// .claude/mcp.json or ~/.config/claude/mcp.json
{
  "mcpServers": {
    "polaris": {
      "command": "python3",
      "args": ["-m", "adapters.mcp_polaris.server"],
      "cwd": "/absolute/path/to/Polaris"
    }
  }
}
```

### Codex CLI

```toml
# ~/.codex/config.toml
[[mcp_servers]]
name = "polaris"
command = "python3"
args = ["-m", "adapters.mcp_polaris.server"]
cwd = "/absolute/path/to/Polaris"
```

### Cursor

Cursor's MCP support currently requires configuring via Settings → MCP → Add. Point it at the same `python3 -m adapters.mcp_polaris.server` command.

## Contract

- **Tool name**: `polaris_lookup`
- **Inputs**: `error_text` (required), `ecosystem` (optional enum), `limit` (1-5)
- **Output**: JSON string with `patterns` list + `_budget` + `_latency_ms`
- **Budget guarantee**: `_budget.used_tokens_est ≤ 300` (NARRATIVE §3)

## What this adapter does NOT do

- Does not write evidence back to `experience-packs-v4/`. That belongs to `eval/evidence_writer.py` (not yet built).
- Does not learn from new errors online. Pattern additions go through the curator + human review.
- Does not implement semantic/embedding match. Regex-only is a deliberate v1 choice for latency and auditability.

## Renaming note

The Python module is `adapters.mcp_polaris` (underscore), directory on disk is `adapters/mcp-polaris` (hyphen) for friendlier CLI. Python path resolution uses the underscore name via `__init__.py` shims below.
