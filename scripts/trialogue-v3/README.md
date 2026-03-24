# Trialogue v3

Multi-agent transcript broker with 7-layer defense-in-depth hardening.

Two vendor CLI agents collaborate through a transcript protocol. The broker sits between them: collecting, sanitizing, and routing transcripts. Agents never share execution environments — cooperation happens through artifact exchange, not filesystem access.

## Threat model

The system assumes any agent may be compromised or produce adversarial output. The broker treats all agent-generated content as untrusted input.

Defense layers are independent — each layer fails without cascading into the next:

| Layer | Component | Function | Implementation |
|-------|-----------|----------|----------------|
| **L1** | Transcript Sanitizer | Strip structural injection patterns before prompt injection | `hardening.py:_sanitize_text_once()` |
| **L2** | Sandbox Isolation | Per-agent OS user, HOME, workspace, TMPDIR | `launcher.sh`, `start.sh` |
| **L3** | Operation Classifier + Locks | Broker-managed mutual exclusion on host-shared resources | `hardening.py:classify_operation()`, `acquire_lock()` |
| **L4** | Version Gate | Binary SHA-256 verification at startup + runtime recheck | `hardening.py:check_version_gate()`, `recheck_version()` |
| **L5** | Local Audit Anchor | Append-only SHA-256 hash chain with HMAC signatures | `hardening.py:append_summary_chain()` |
| **L6** | Remote Audit Anchor | Independent sink process with credential-separated publish/verify | `remote_anchor_sink.py`, `hardening.py:publish_remote_anchor()` |
| **L7** | Cross-Audit | Per-turn digest comparison between agents | `server.py:_apply_remote_verifier_result()` |

Design principle: L1 blocks the cheapest structural injections. Semantic attacks that bypass L1 hit L2 (sandbox limits blast radius), L3 (locks constrain host operations), and L5–L7 (full audit trail makes all behavior traceable).

## Sanitizer details

`_sanitize_text_once()` applies 5 rules in order:

1. **Invisible Unicode stripping** — 32+ character classes (zero-width, bidi overrides, variation selectors)
2. **Block wrapper stripping** — Stack-based tag matcher for 6 registered wrappers (`MEMORY-CONTEXT`, `MEETING-CONTEXT`, `TARGET-CONTEXT`, `SYSTEM-PROMPT`, `SYSTEM-MESSAGE`, `ASSISTANT-PROMPT`). Handles nesting, cross-nesting, orphaned tags. Case-insensitive. 500-layer nesting tested, no ReDoS.
3. **Audit header stripping** — Line-level regex for `[TRIALOGUE-AUDIT]` headers
4. **LLM format pattern stripping** — 7 anchored regexes for non-bracket prompt formats (ChatML, Llama 2, Copilot, Markdown heading). Block-only matching (`^...$` + `re.MULTILINE`) to avoid inline false positives.
5. **Whitespace compression** — 3+ consecutive newlines → 2

Three modes: `strict` (detect + delete, default), `permissive` (detect + preserve), `disabled`.

Patterns are loaded from `sanitizer-patterns.json` (external config, hot-reloadable) with code-level defaults as fallback.

### Known limitation (W11)

The `^###\s*System:\s*.*$` pattern matches inside markdown code blocks due to `re.MULTILINE` — `^` anchors to any line start, not just block start. Benchmark confirms 1/10 LLM-format-discussion benign samples affected. Benign Utility: 96.7% (within gate). This is a documented trade-off, not a silent failure.

## Remote audit anchor

```
Broker (publish.token, write-only)
    │
    │  POST /append
    ▼
Sink (independent process, independent user)
    │  SQLite WAL, synchronous=FULL
    │  Sequence: per-room gapless increment
    │  Idempotent: same (room_id, rid, sha) → 200
    │  Conflict:   same (room_id, rid), different sha → 409
    │
    │  GET /verify
    ▲
Broker (verify.token, read-only)
```

Agents hold no tokens. Sink is unreachable from agent processes.

**Verify** compares local chain vs remote records field-by-field (6 checkpoints per entry): record count, sequence continuity, room_id, genesis hash, prev_summary_sha256, turn_summary_sha256.

**State machine**: `healthy` → `degraded` (backlog pending) → `anchor_blocked` (hard cap exceeded / blocking mode 3× unanchored / verify mismatch) → `read_only_diagnostic` (startup verify mismatch). Recovery requires system self-heal + operator manual `reset_recovery()`.

## Injection benchmark

100 attack payloads (AgentDojo taxonomy adaptation: 25 IPI + 25 SMS + 25 TKI + 25 IND) + 30 benign payloads (20 engineering Q&A + 10 LLM format discussion).

| Metric | Value | Gate |
|--------|-------|------|
| SMS L1 detection | 96% (24/25) | ≥80% ✓ |
| Marker Residue Rate (proxy lower bound) | 36% | <50% ✓ |
| Payload Unmodified Rate (upper bound) | 76% | — |
| Benign Utility (total) | 96.7% (29/30) | ≥90% ✓ |
| Benign Utility (engineering Q&A) | 100% (20/20) | ≥95% ✓ |

36 marker residuals: 34 semantic-level (IPI/TKI/IND — sanitizer by design does not cover), 2 structural SMS. Semantic attacks are mitigated by L2–L7, not L1.

This is not an official AgentDojo score. It is an adapted evaluation using the same 4-category injection taxonomy.

## Adversarial test suite

176 checks across 14 test files, zero failures.

| Suite | Checks | Coverage |
|-------|--------|----------|
| `hardening_adversarial.py` | 50 | Sanitizer bypass, version gate, operation locks, classifier evasion, event log, config boundary |
| `hardening_adversarial_r2.py` | 48 | Zero-width, CRLF, orphan tags, ReDoS, TOCTOU, lock deep adversarial, concurrent log |
| `hardening_injection_benchmark.py` | 130 | 100 attack + 30 benign payloads, dual-layer measurement |
| `hardening_p1_adversarial.py` | 49 | Hash chain tampering, signature forgery, verifier bypass, atomic write, port registry, concurrent chain |
| `hardening_p1_recheck_adversarial.py` | 29 | Runtime binary replacement detection, policy coupling, stat short-circuit |
| `hardening_p1_*.py` (smoke) | 3 files | Anchor export, recovery flow, shared host isolation |
| `hardening_p2_*.py` | 5 files | Remote sink append/verify, broker state machine, operator recovery |
| `hardening_smoke.py` | — | Fast pre-commit sanity check |

All tests run against live broker configuration path, not source-tree defaults.

## Documented weaknesses

11 weaknesses publicly mapped. Each maps to specific defense layers.

| ID | Description | L1 blocks? | Mitigation | Status |
|----|-------------|:---:|------------|--------|
| W1 | Semantic/rhetorical injection | ✗ | L2+L3+L7 | Sandbox fallback |
| W2 | Invisible Unicode bypass | ✓ | L1 | Fixed |
| W3 | Homoglyph attacks | ✗ | L1 partial + L2 | Future work |
| W4 | Multi-turn fragmented injection | ✗ | L5+L6+L7 | Future work |
| W5 | Unregistered wrapper tags | ✓ | L1 | Fixed, live-verified |
| W6 | HTML/Markdown hiding | ✗ | L2 | Sandbox fallback |
| W7 | Base64/encoding bypass | ✗ | L2+L5 | Sandbox fallback |
| W8 | Tag attribute injection | ✓ | L1 | Tested |
| W9 | Ultra-long payload DoS | ✓ | L1 | Tested (100KB, 500-layer) |
| W10 | Natural language resembling instructions | — | L7 | Design tolerance |
| W11 | LLM format rule false positive | — | L1 side effect | Known limitation |

## File structure

```
Core runtime
├── server.py                  Broker main (state machine, remote anchor, recovery)
├── chat.py                    Chat UI / transcript routing
├── launcher.sh                Runner launcher (sandbox, TMPDIR isolation)
├── _audit.py                  Audit log / session confirmation
├── _memory.py                 Agent memory
├── hardening.py               Security core (~2000 lines)
├── sanitizer-patterns.json    Sanitizer config (synced to live broker)

Remote audit anchor
├── remote_anchor_sink.py      Sink HTTP server (SQLite WAL)
├── remote_anchor_verifier.py  Standalone chain verifier
├── start-remote-anchor-sink.sh
├── remote-anchor-sink.conf.example

Startup / deploy
├── start.sh                   tmux session launcher
├── start-web.sh               Web UI launcher
├── deploy-level2.sh           Level 2 deployment (per-agent OS users)
├── codex-runner.sh            Codex CLI runner wrapper
├── codex_app_server_runner.py Codex app server integration

Adversarial tests (14 files)
├── hardening_smoke.py                    Pre-commit sanity
├── hardening_adversarial.py              50 checks: sanitizer, gate, locks, classifier
├── hardening_adversarial_r2.py           48 checks: unicode, ReDoS, TOCTOU, deep adversarial
├── hardening_injection_benchmark.py      130 payloads: AgentDojo taxonomy adapted
├── hardening_p1_adversarial.py           49 checks: chain, signatures, ports, concurrency
├── hardening_p1_recheck_adversarial.py   29 checks: runtime binary replacement
├── hardening_p1_anchor_smoke.py          Anchor export smoke
├── hardening_p1_recovery_smoke.py        Recovery flow smoke
├── hardening_p1_shared_host_smoke.py     Shared host isolation smoke
├── hardening_p1_attack.py                Attack surface tests
├── hardening_p2_broker_anchor_smoke.py   Broker anchor state machine
├── hardening_p2_publish_smoke.py         Remote publish pipeline
├── hardening_p2_sink_smoke.py            Sink append/verify
├── hardening_p2_verifier_smoke.py        Verifier integration
├── hardening_p2_operator_smoke.py        Operator recovery

Config / tools
├── trialogue-v3.conf.example             Config template
├── runner-version-allowlist.json         Allowed runner binary hashes
├── verify-rid.sh                         Request ID verification
├── verify-summary-chain.py               Standalone chain integrity check
├── index.html                            Web UI
```

## Configuration

```bash
cp trialogue-v3.conf.example trialogue-v3.conf
```

`trialogue-v3.conf` is gitignored. Key settings:

| Key | Default | Function |
|-----|---------|----------|
| `HARDENING_SANITIZER` | `strict` | Sanitizer mode |
| `HARDENING_VERSION_GATE` | `warn` | Binary verification policy |
| `HARDENING_REMOTE_AUDIT_PUBLISH` | `disabled` | Remote anchor mode: disabled / async / blocking |
| `HARDENING_REMOTE_AUDIT_HARD_CAP` | `500` | Backlog entries before blocking new turns |
| `HARDENING_REMOTE_AUDIT_VERIFY_INTERVAL_TURNS` | `10` | Turns between remote verification (max 50) |
| `HARDENING_SANITIZER_PATTERNS` | (auto) | Path to sanitizer-patterns.json |

Full configuration reference: 11 remote anchor keys documented in `hardening.py:load_hardening_settings()`.

## Running

```bash
# Start broker + agents
bash start.sh "discussion topic"

# Start web UI
bash start-web.sh

# Start remote anchor sink (independent process)
bash start-remote-anchor-sink.sh

# Run all adversarial tests
python3 hardening_adversarial.py
python3 hardening_adversarial_r2.py
python3 hardening_injection_benchmark.py
python3 hardening_p1_adversarial.py
python3 hardening_p1_recheck_adversarial.py

# Verify chain integrity (standalone)
python3 verify-summary-chain.py /path/to/room.jsonl
```

## Architecture documentation

Detailed technical specifications are maintained in `trialogue-docs/architecture/`:

- `trialogue-v3-sanitizer-defense-map.md` — Sanitizer implementation details, 11-weakness defense mapping, benchmark results, remote anchor full spec
- `trialogue-v3-hardening-plan.md` — Phase-gated hardening strategy (P0/P1/P2)

---

*Author: Zihang Zhao*
*Version: v3 (2026-03-24)*
*Test baseline: 176 adversarial checks + 130 benchmark payloads, zero failures*
