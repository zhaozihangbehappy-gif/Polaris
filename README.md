# Polaris

Polaris stops your AI coding agent from repeating the same mistakes. Open source, local-first, MIT-licensed. A growing library of verified failure patterns, reviewed by the people who use them.

## Install

git clone https://github.com/zhaozihangbehappy-gif/Polaris.git && cd Polaris && python -m pip install -r adapters/mcp-polaris/requirements.txt

Windows: if `python` is not registered, use `py -m pip install -r adapters/mcp-polaris/requirements.txt`.
Linux/macOS: if your system also has Python 2, use `python3 -m pip`.

## MCP client config

Use the installed `polaris` command as the stable MCP entrypoint:

```json
{
  "mcpServers": {
    "polaris": {
      "command": "polaris",
      "args": ["serve-mcp"]
    }
  }
}
```

### Legacy / dev mode

Requires cwd at repo root; not recommended for production use.

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

## Contribute

Polaris gets better every time someone catches a failure it didn't know about. If Polaris saved you a loop, or you hit a failure that belongs in the library, you can help the next person skip it:

- `polaris submit <your-pattern.json>` — propose a new candidate. Accepts either a full v4 pattern record or a `schema_version: 1` contribution file exported by `polaris_cli.py experience contribute` (auto-converted).
- `polaris confirm <pattern_id>` — tell the project a candidate actually helped you on a real case.
- `polaris reject <pattern_id>` — tell the project a candidate was wrong or harmful.
- `polaris promote` — move confirmed candidates into the community pool.

> Legacy: the same commands are also available via `python3 scripts/polaris_community.py ...` for now.

A candidate joins Polaris's shared library after **≥ 2 independent users** confirm it helped them and no one rejected it. The shared library has three tiers — `official` (internal verified-live), `community` (community-verified through this channel), and `candidate` (unconfirmed but shipped so users can try them). All three are loaded at lookup time; each match carries its tier. Nobody's agent runs through a central server; confirmations are opt-in. See `community/README.md` for how trust and promotion work.

The shipped `candidate` tier now covers all 8 ecosystems. The `official` tier remains the audited baseline, while candidate breadth grows faster through releases and community submissions.

## Read these, not the rest

- START_HERE.md
- FACTS.md
- INSTALL.md

There's an `archive/` folder too. It's old audit work I kept public so anyone can check it. Don't read it to learn how Polaris works — the three files above are the whole product.

There's also an `eval/` folder with historical evaluation fixtures and logs. Public, useful for auditing, not required for install or everyday use.

## Maintenance

Solo-maintained, best-effort response. Issues and PRs typically get a reply within a week. If something is blocking you, say so in the issue and it gets looked at sooner.

## Sponsor

If Polaris saved you time and you want to chip in, pay what you want (minimum $1) at https://<YOUR_HANDLE>.gumroad.com/l/polaris. It's optional — the full library and tooling are MIT-licensed and will stay that way.

## License

MIT
