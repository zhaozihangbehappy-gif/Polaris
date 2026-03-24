# Trialogue v4

External content ingestion gateway for AI coding agents.

v4 sits between the internet and your agent. All external content (web pages, search results, curl downloads) passes through a sanitizing pipeline before entering agent context. Structural prompt injection is stripped. Each ingestion is appended to a local SHA-256 hash chain for audit.

Audit modes: `local` (best-effort — failure surfaces metadata), `strict` (failure blocks pipeline — no content delivered), `disabled` (skip audit). Remote audit anchors can publish chain head hashes to webhook or file sinks.

This directory is a complete, independent copy of the Trialogue codebase. v3 (multi-agent transcript broker) is frozen separately. v4 adds the ingestion gateway layer on top of the inherited v3 code.

## Architecture

```
Agent (Claude Code / Codex)
    │
    ├── MCP tools: trialogue_fetch / trialogue_search (primary path)
    │       Content → pipeline → tsan sanitize → audit chain → return
    │
    └── Direct access: WebFetch / WebSearch / curl / wget
            PreToolUse hooks intercept (enforced routing)
            ├── WebFetch → deny + sanitized content in reason
            ├── WebSearch → passthrough (no endpoint) / deny + sanitized (with endpoint)
            └── curl/wget → deny (POST/localhost allowed)
```

### Honest constraints

- Claude Code PreToolUse hooks cannot do transparent tool result substitution. Hooks deny + provide cleaned content in the reason field. The agent knows it was intercepted.
- Codex: `trialogue guard on` registers the MCP server via `codex mcp add` (smoke-tested, MCP fetch verified). However, Codex lacks PreToolUse hooks, so there is no enforced routing — the agent must voluntarily use `trialogue_fetch`/`trialogue_search`.
- The curl whitelist allows POST, request body, and localhost. Everything else is blocked, including authenticated GET, `-o`, and piped commands. **Pattern matching is a cat-and-mouse game** — `bash -c "curl ..."`, variable splicing, `python3 -c "urllib..."`, `nc`/`socat` can bypass. Use `--egress` with root on dedicated hosts for kernel-level network control.
- `guard on` now detects WebFetch/WebSearch in Claude Code allowlist and **hard-fails** (non-zero exit). Use `--fix` to auto-remove conflicting entries.

## Quick start

```bash
# Enable guard (one command — writes Claude Code settings; registers Codex MCP if installed)
python3 trialogue guard on

# If WebFetch/WebSearch are in your allowlist, --fix removes them
python3 trialogue guard on --fix

# Now start claude or codex normally — guard is active
claude

# Check status
python3 trialogue status

# Disable guard (preserves audit data)
python3 trialogue guard off
```

`trialogue guard on` does 8 things automatically:
1. Checks for allowlist conflicts (hard-fails if WebFetch/WebSearch are allowlisted)
2. Writes MCP server config to Claude Code `settings.json`
3. Writes PreToolUse hooks for WebFetch/WebSearch/Bash
4. Registers MCP server with Codex via `codex mcp add` (if installed)
5. Precompiles Python to `.pyc`
6. Generates default `trialogue-v4.conf` if missing
7. Verifies MCP server responds to initialize handshake
8. Enables network egress control (with `--egress` flag + root, dedicated hosts only)

## Deployment modes

Trialogue has two enforcement layers. Choose based on your environment:

### Default: hook enforcement (all environments)

```bash
python3 trialogue guard on
```

PreToolUse hooks intercept Claude Code's WebFetch, WebSearch, and Bash (curl/wget) tool calls. Agent requests are denied and routed through the sanitizing pipeline. This is the correct mode for:

- **Desktop / laptop development machines**
- **Environments with HTTP proxies** (corporate proxy, Clash, V2Ray, etc.)
- **WSL2 / shared workstations**

Hook enforcement operates at agent behavior level — it blocks agent tool calls without affecting the user's own network access. No root required.

### Optional: kernel egress (`--egress`, dedicated hosts only)

```bash
sudo python3 trialogue guard on --egress
```

Adds iptables owner match rules: only the `_trialogue` system user can reach external HTTP/HTTPS. All other UIDs are rejected at kernel level. This closes pattern-matching bypass vectors (nc, socat, python urllib, etc.).

**Use only on:**
- Dedicated agent runner machines
- CI / headless hosts
- Environments where no human user needs direct outbound HTTP on the same machine

**Do not use on:**
- Desktop machines with a global HTTP proxy — blocking the proxy port cuts all network access, including the user's own
- Shared workstations where other users or services need outbound HTTP
- Any machine where `$http_proxy` / `$https_proxy` is set to a non-localhost address

The `--egress` flag auto-detects proxy environment and includes proxy ports in the controlled set. If your environment routes all traffic through a proxy, `--egress` will effectively become a machine-wide network kill switch — this is by design (kernel egress is meant for single-purpose hosts), but wrong for desktop use.

When `--egress` is run without root, or when iptables rules fail to install, it degrades gracefully to hook-only mode with a clear warning. No silent failures.

## Configuration

```bash
cp trialogue-v4.conf.example trialogue-v4.conf
```

| Key | Default | Function |
|-----|---------|----------|
| `audit_mode` | `local` | `local` (best-effort) / `strict` (failure blocks) / `disabled` |
| `max_response_bytes` | `524288` | Max fetch size (512KB) |
| `default_timeout` | `15` | HTTP timeout in seconds |
| `sanitizer_mode` | `strict` | `strict` / `permissive` / `report` |
| `search_endpoint` | (empty) | Search API URL — WebSearch passthrough when empty |
| `remote_anchor_sink` | (empty) | `webhook` or `file` — publish chain head to external sink |
| `remote_anchor_url` | (empty) | Webhook URL or file path for anchor publish |
| `remote_anchor_interval` | `0` | Publish every N ingestions (0 = every) |

Config is read at pipeline import time. Override path via `TRIALOGUE_CONF` env var.

## Components

| File | Purpose |
|------|---------|
| `tsan` | Zero-dependency standalone sanitizer CLI |
| `pipeline.py` | 7-step ingestion pipeline (fetch → HTML strip → sanitize → audit → return) |
| `mcp-server.py` | MCP JSON-RPC server (stdio, lazy imports, ~100ms cold start) |
| `audit.py` | SHA-256 ingestion audit chain + remote anchor publish |
| `config.py` | Runtime config loader (`trialogue-v4.conf`) |
| `egress.py` | Network egress control (iptables owner match, user isolation) |
| `hooks/intercept-webfetch.sh` | PreToolUse hook: block WebFetch, return sanitized content |
| `hooks/intercept-websearch.sh` | PreToolUse hook: passthrough or block WebSearch |
| `hooks/intercept-curl.sh` | PreToolUse hook: block external curl/wget |
| `trialogue` | Unified CLI (`guard on/off`, `start/stop`, `status`) |
| `hardening.py` | Inherited v3 security core (sanitizer, chain ops, patterns) |

## Ingestion pipeline

```
① Fetch URL (urllib, 512KB max, binary rejection)
② HTML → plain text (script/style discarded, code blocks preserved)
③ tsan sanitize (invisible unicode, block wrappers, LLM format patterns)
④ Source tag + SHA-256 hashes (raw + cleaned)
⑤ Audit chain append (seq, prev_hash, entry_hash — tamper-detectable)
⑥ Return cleaned text + metadata
```

Audit behavior depends on `audit_mode`:
- **local** (default): best-effort — audit failure surfaces `audit_status: "failed"` + `audit_error` metadata, content still returned. MCP appends WARNING.
- **strict**: audit failure blocks the pipeline — `cleaned_text` is empty, MCP returns error. No content leaks without audit trail.
- **disabled**: skip chain writes entirely.

Remote anchor publish (⑥b) sends chain head hash to webhook or file sink after each ingestion (configurable interval). In strict mode, anchor publish failure also blocks.

## Test suite

490 checks across 18 test files, zero failures.

| Test file | Checks | Coverage |
|-----------|--------|----------|
| `tsan_vs_v3_parity.py` | 130 | tsan vs hardening.py parity on 130 benchmark payloads |
| `tsan_cli_test.py` | 21 | CLI: stdin/file/json/modes/exit codes/performance |
| `html_strip_test.py` | 19 | HTML→text: script discard, code preserve, entities, block tags |
| `fetch_injection_test.py` | 33 | Full pipeline: injection removal, audit hot-path, metadata |
| `mcp_protocol_test.py` | 33 | MCP JSON-RPC: initialize, tools/list, tools/call, errors |
| `hook_webfetch_test.py` | 10 | WebFetch hook: intercept, sanitize, routing |
| `hook_websearch_test.py` | 4 | WebSearch hook: passthrough, non-target ignore |
| `hook_curl_test.py` | 28 | curl whitelist: POST/body/localhost allow, everything else block |
| `ingestion_chain_test.py` | 31 | Chain continuity, tamper detection, isolation, via_guard |
| `config_test.py` | 19 | Config loader, defaults, env override, pipeline wiring |
| `codex_mcp_test.py` | 9 | Codex MCP: add/remove/list + MCP fetch e2e |
| `audit_failure_test.py` | 16 | Audit three-state: ok/failed/disabled + strict mode blocking |
| `trialogue_cli_test.py` | 42 | CLI: guard on/off, hooks, idempotent, status, allowlist conflict, --egress |
| `pipeline_degrade_test.py` | 23 | Edge cases: unreachable, empty, unicode, large, modes |
| `egress_test.py` | 16 | Network egress control: status, degradation, CLI, MCP config invariant |
| `anchor_test.py` | 21 | Remote audit anchor: webhook sink, file sink, failure, empty chain |
| `search_endpoint_test.py` | 12 | Search endpoint: clean/injected results, no-endpoint fallback |
| `e2e_component_test.py` | 20 | Component e2e: MCP→pipeline→audit→hooks full path |

Plus `e2e_harness_test.sh` for real Claude Code harness verification (manual/semi-automated).

## Inherited from v3

This directory contains the complete v3 codebase (broker, sandbox, audit layers L1-L7). v4-specific files are listed above. v3 files are frozen — v4 does not modify them.

v3 test suite (194 checks) runs independently from the v3 directory.

---

*Author: Zihang Zhao*
*Version: v4 fully hardened final (2026-03-24)*
*Test baseline: 490 v4 checks (incl. 130 parity) across 18 test files, zero failures*
*Kernel egress verified on WSL2 with root (iptables + _trialogue user + sudoers + MCP re-verify)*
