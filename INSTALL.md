# Install

Polaris runs locally as an MCP tool. No server, no account. Clone, install, drop a config block into your agent, confirm it's alive.

## 1. Clone and install

```
git clone https://github.com/zhaozihangbehappy-gif/Polaris.git
cd Polaris
python -m pip install -r adapters/mcp-polaris/requirements.txt
```

Python 3.10+. If you want an isolated env, `venv` or `uv` — either is fine.
Windows: if `python` is not registered, use `py -m pip install -r adapters/mcp-polaris/requirements.txt`.
Linux/macOS: if your system also has Python 2, use `python3 -m pip`.

## 2. Wire it to your agent

Replace `/absolute/path/to/Polaris` with wherever you cloned.

### Claude Code

Edit `~/.config/claude/mcp.json` (or `.claude/mcp.json` in your project):

```json
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

Restart Claude Code.

### Codex CLI

Append to `~/.codex/config.toml`:

```toml
[mcp_servers.polaris]
command = "python3"
args = ["-m", "adapters.mcp_polaris.server"]
cwd = "/absolute/path/to/Polaris"
```

### Cursor

Edit `~/.cursor/mcp.json` (create it if missing):

```json
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

Restart Cursor.

## 3. Confirm it's alive

Before touching an agent, run the adapter by itself:

```
python3 -c "from adapters.mcp_polaris.polaris_index import match, format_for_injection; print(format_for_injection(match(\"ModuleNotFoundError: No module named 'requests'\", ecosystem='python')))"
```

You should see JSON with a `patterns` list and a `_budget` field. If that prints, the index loads and the matcher works.

Now try it through your agent:

> I'm getting `ModuleNotFoundError: No module named 'requests'` in a Python project. Check Polaris before you guess.

If the agent calls `polaris_lookup` and a matching pattern comes back, you're done. If it doesn't call the tool, the agent hasn't picked up the MCP config — recheck the path, the `cwd`, and restart the agent.

## Uninstall

Remove the `polaris` block from whichever config file above. Delete the cloned directory. That's it.
