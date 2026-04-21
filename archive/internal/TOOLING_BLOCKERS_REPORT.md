# Tooling Blockers Report (v4)

Generated: 2026-04-20
Environment: WSL2 (Linux 6.6.87.2-microsoft-standard-WSL2)

## Patterns blocked by missing toolchains

| Ecosystem | Patterns | Missing binaries |
|---|---:|---|
| docker | 121 | `docker` (symlink → agent-runtime-guard, no real binary resolvable) |
| go | 78 | `go` (symlink only) |
| java | 71 | `java`, `javac`, `mvn`, `gradle` (all symlinks only) |
| terraform | 34 | `terraform` (symlink only) |
| ruby | 30 | `ruby`, `gem`, `bundle` (all symlinks only) |
| **total** | **334** | |

These patterns are marked `authoring_blocked_tooling_unavailable` and are
NOT passed to Codex — no fake fixture is authored; no sandbox validation
is attempted.

## Probe evidence

Every probed command resolved via `~/bin/<tool>`, which is a symlink to
`agent-runtime-guard`. The guard falls through to the real binary if found
on PATH; for the five ecosystems above, `which -a <tool>` on WSL returned
only the guard link itself, and `find /usr /opt -name <tool> -executable
-type f` returned nothing.

```
$ go version
agent-runtime-guard: could not resolve real binary for go

$ docker --version
agent-runtime-guard: could not resolve real binary for docker
```

## Install recommendations (host-side)

Below each tool is the cheapest install that lets `scripts/author_fixtures.py`
cover the relevant ecosystem. All commands require sudo on WSL.

```bash
# docker (121 patterns)
sudo apt-get update && sudo apt-get install -y docker.io
# go (78 patterns)
sudo apt-get install -y golang-go
# java + maven + gradle (71 patterns)
sudo apt-get install -y default-jdk maven gradle
# terraform (34 patterns)
sudo apt-get install -y wget gnupg
wget -O- https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp.gpg
echo "deb [arch=amd64 signed-by=/usr/share/keyrings/hashicorp.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt-get update && sudo apt-get install -y terraform
# ruby (30 patterns)
sudo apt-get install -y ruby ruby-bundler
```

After install, `scripts/author_fixtures.py` without `--only-sandboxable` will
pick these up and author real fixtures for the remaining 334 patterns.

## Container fallback option

If host-side installs are not acceptable, author_fixtures.py can be extended
to run each `verification_command` inside a per-pattern container image (for
example `docker run --rm -v <workdir>:/w -w /w golang:1.22 go build ./...`).
This requires docker itself to be installed; once it is, the pipeline can
build tooling images on-the-fly per ecosystem and keep the host clean.

Container fallback is NOT yet implemented — it is tracked as a follow-up,
not a current capability. All 334 blocked patterns remain blocked in this
run.

## What is NOT blocked

```
python  → 148 patterns — python3 usable
node    → 145 patterns — node usable
rust    → 70 patterns — cargo/rustc usable
total   → 363 patterns — currently sandboxable
```

The authoring pipeline reached 51 of these 363 before Codex rate-limited
(see `AUTHORING_REPORT.md` for the failure breakdown). After quota resets
the remaining 312 sandboxable patterns can be authored without any tooling
changes.
