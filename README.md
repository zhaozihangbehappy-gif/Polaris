# Polaris

Polaris stops your AI coding agent from repeating the same mistakes. Open source. Pay $2.49 once if it saves you a loop.

## Install

git clone https://github.com/zhaozihangbehappy-gif/Polaris.git && cd Polaris && python -m pip install -r adapters/mcp-polaris/requirements.txt

Windows: if `python` is not registered, use `py -m pip install -r adapters/mcp-polaris/requirements.txt`.
Linux/macOS: if your system also has Python 2, use `python3 -m pip`.

## Pay

https://<YOUR_HANDLE>.gumroad.com/l/polaris

One payment. Forever. The receipt email is your proof of support. No account, no login.

## Contribute

Polaris grows through the people who use it. If Polaris saved you a loop — or if you hit a failure it didn't know about — you can add it:

- `python3 scripts/polaris_community.py submit <your-pattern.json>` — propose a new candidate. Accepts either a full v4 pattern record or a `schema_version: 1` contribution file exported by `polaris_cli.py experience contribute` (auto-converted).
- `python3 scripts/polaris_community.py confirm <pattern_id>` — tell the project a candidate actually helped you on a real case.
- `python3 scripts/polaris_community.py reject <pattern_id>` — tell the project a candidate was wrong or harmful.

A candidate joins Polaris's shared library after **≥ 2 independent users** confirm it helped them and no one rejected it. The shared library has three tiers — `official` (internal verified-live), `community` (community-verified through this channel), and `candidate` (unconfirmed but shipped so users can try them). All three are loaded at lookup time; each match carries its tier. Nobody's agent runs through a central server; confirmations are opt-in. See `community/README.md` for how trust and promotion work.

The shipped `candidate` tier now covers all 8 ecosystems. The `official` tier remains the audited baseline, while candidate breadth grows faster through releases and community submissions.

## Read these, not the rest

- START_HERE.md
- FACTS.md
- INSTALL.md

There's an `archive/` folder too. It's old audit work I kept public so anyone can check it. Don't read it to learn how Polaris works — the three files above are the whole product.

There's also an `eval/` folder with historical evaluation fixtures and logs. Public, useful for auditing, not required for install or everyday use.

## License

MIT
