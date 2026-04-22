from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import requests

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

try:
    import tomli_w
except ModuleNotFoundError:  # pragma: no cover
    tomli_w = None  # type: ignore[assignment]

from polaris import paths, supporter
from polaris.adapter import server as adapter_server
from polaris.adapter.index import load_index, match
from polaris.community import (
    _fingerprint,
    cmd_confirm,
    cmd_promote,
    cmd_reject,
    cmd_submit,
)

RULE_SNIPPET = "before guessing at an error, call polaris_lookup"
RULE_BLOCK = (
    "# >>> polaris managed >>>\n"
    f"{RULE_SNIPPET}\n"
    "# <<< polaris managed <<<\n"
)
RELEASE_REPO = os.getenv("POLARIS_RELEASE_REPO", "zhaozihangbehappy-gif/Polaris")
RELEASES_API_URL = f"https://api.github.com/repos/{RELEASE_REPO}/releases"


def _toml_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    raise TypeError(f"unsupported TOML value: {value!r}")


def _dump_toml(data: dict[str, Any]) -> str:
    if tomli_w is not None:
        return tomli_w.dumps(data)
    # Minimal fallback: write top-level scalars + a single [mcp_servers.<name>]
    # block per key. Only used in dev (tomli_w is a hard dep in pyproject).
    lines: list[str] = []
    nested: dict[str, dict[str, Any]] = {}
    for key, value in data.items():
        if key == "mcp_servers" and isinstance(value, dict):
            nested = value
            continue
        lines.append(f"{key} = {_toml_value(value)}")
    for srv_name, srv_cfg in nested.items():
        lines.append(f"[mcp_servers.{srv_name}]")
        for subkey, subval in srv_cfg.items():
            lines.append(f"{subkey} = {_toml_value(subval)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _config_spec() -> dict[str, Any]:
    return {"command": "polaris", "args": ["serve-mcp"]}


def _wsl_bridge_spec() -> dict[str, Any]:
    # Windows-side agent (Cursor/Claude Desktop) calls into the WSL install
    # via the `wsl` shim. When `wsl` runs a command non-interactively, the
    # default PATH does NOT include ~/.local/bin (where pipx installs
    # polaris), so resolve the absolute path at install time and pass it
    # through -e so wsl treats it as an exec target, not shell input.
    polaris_abs = shutil.which("polaris") or "polaris"
    return {"command": "wsl", "args": ["-e", polaris_abs, "serve-mcp"]}


def _is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _wsl_windows_home() -> Path | None:
    # Return /mnt/c/Users/<name> if resolvable; else None.
    if not _is_wsl():
        return None
    winuser = os.environ.get("WINUSER") or os.environ.get("USER") or ""
    candidates = []
    if winuser:
        candidates.append(Path(f"/mnt/c/Users/{winuser}"))
    users_root = Path("/mnt/c/Users")
    if users_root.exists():
        for entry in users_root.iterdir():
            if entry.is_dir() and entry.name not in ("Public", "Default", "All Users"):
                candidates.append(entry)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _json_config_path(agent: str) -> Path | None:
    mapping = {
        "claude-code": Path.home() / ".config" / "claude" / "mcp.json",
        "cursor": Path.home() / ".cursor" / "mcp.json",
    }
    return mapping.get(agent)


def _windows_json_config_path(agent: str) -> Path | None:
    # Windows-side config path reachable from WSL via /mnt/c. Only
    # meaningful for GUI agents whose Windows install reads C:\Users\<user>.
    home = _wsl_windows_home()
    if home is None:
        return None
    mapping = {
        "cursor": home / ".cursor" / "mcp.json",
        "claude-code": home / ".claude.json",
    }
    return mapping.get(agent)


def _rules_path(agent: str, cwd: Path) -> Path:
    mapping = {
        "claude-code": cwd / "CLAUDE.md",
        "codex": cwd / "AGENTS.md",
        "cursor": cwd / ".cursorrules",
    }
    return mapping[agent]


def _codex_config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def _backup(path: Path) -> None:
    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_mcp(path: Path, spec: dict[str, Any], dry_run: bool) -> str:
    data = _load_json(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    servers["polaris"] = spec
    preview = json.dumps({"mcpServers": {"polaris": spec}}, indent=2)
    if dry_run:
        return f"[dry-run] would merge {path}\n{preview}"
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return f"merged {path}\n{preview}"


def _install_json_agent(agent: str, dry_run: bool) -> str:
    outputs: list[str] = []
    linux_path = _json_config_path(agent)
    assert linux_path is not None
    outputs.append(_write_json_mcp(linux_path, _config_spec(), dry_run))
    win_path = _windows_json_config_path(agent)
    if win_path is not None:
        outputs.append(
            _write_json_mcp(win_path, _wsl_bridge_spec(), dry_run)
            + f"\n(windows-side via wsl bridge — agent running on Windows will call `wsl -e <polaris-abs-path> serve-mcp`)"
        )
    return "\n\n".join(outputs)


def _install_codex_agent(dry_run: bool) -> str:
    # Codex CLI expects mcp_servers as a TOML map: [mcp_servers.<name>] with
    # command/args. Older releases accepted [[mcp_servers]] with a `name`
    # key; current versions reject that with "expected a map" and refuse
    # to load the entire config. We migrate any legacy list form on write.
    path = _codex_config_path()
    data: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = tomllib.loads(path.read_text())
            if isinstance(loaded, dict):
                data = loaded
        except tomllib.TOMLDecodeError:
            data = {}
    servers = data.get("mcp_servers")
    if isinstance(servers, list):
        migrated: dict[str, dict[str, Any]] = {}
        for srv in servers:
            if isinstance(srv, dict) and isinstance(srv.get("name"), str):
                name = srv["name"]
                migrated[name] = {k: v for k, v in srv.items() if k != "name"}
        servers = migrated
    elif not isinstance(servers, dict):
        servers = {}
    servers["polaris"] = _config_spec()
    data["mcp_servers"] = servers
    preview = _dump_toml({"mcp_servers": {"polaris": servers["polaris"]}})
    if dry_run:
        return f"[dry-run] would merge {path}\n{preview}"
    path.parent.mkdir(parents=True, exist_ok=True)
    _backup(path)
    path.write_text(_dump_toml(data))
    return f"merged {path}\n{preview}"


def _configured_agents() -> dict[str, str]:
    found: dict[str, str] = {}
    for agent in ("claude-code", "cursor"):
        for path in filter(None, (_json_config_path(agent), _windows_json_config_path(agent))):
            if not path.exists():
                continue
            data = _load_json(path)
            servers = data.get("mcpServers")
            if isinstance(servers, dict) and "polaris" in servers:
                key = agent if path == _json_config_path(agent) else f"{agent}-windows"
                found[key] = str(path)
    codex = _codex_config_path()
    if codex.exists():
        try:
            data = tomllib.loads(codex.read_text())
        except tomllib.TOMLDecodeError:
            data = {}
        servers = data.get("mcp_servers")
        has_polaris = False
        if isinstance(servers, dict) and "polaris" in servers:
            has_polaris = True
        elif isinstance(servers, list) and any(
            isinstance(srv, dict) and srv.get("name") == "polaris" for srv in servers
        ):
            has_polaris = True
        if has_polaris:
            found["codex"] = str(codex)
    return found


def _update_rules(agent: str, enable: bool, cwd: Path) -> str:
    path = _rules_path(agent, cwd)
    existing = path.read_text() if path.exists() else ""
    new_text = re.sub(
        r"\n?# >>> polaris managed >>>.*?# <<< polaris managed <<<\n?",
        "\n",
        existing,
        flags=re.DOTALL,
    ).strip("\n")
    if enable:
        if RULE_SNIPPET not in existing:
            new_text = (new_text + "\n\n" + RULE_BLOCK).strip() + "\n"
        else:
            new_text = existing
    else:
        new_text = (new_text + "\n") if new_text else ""
    if path.exists():
        _backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text)
    return str(path)


def _release_assets() -> list[dict[str, Any]]:
    response = requests.get(RELEASES_API_URL, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        return []
    assets: list[dict[str, Any]] = []
    for release in payload:
        if not isinstance(release, dict):
            continue
        for asset in release.get("assets", []):
            if isinstance(asset, dict):
                asset = dict(asset)
                asset["_tag_name"] = release.get("tag_name", "")
                assets.append(asset)
    return assets


def _matching_assets(channel: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict[str, Any]]]:
    assets = _release_assets()
    tarball = None
    checksum = None
    matches = [asset for asset in assets if f"polaris-packs-{channel}-" in str(asset.get("name", ""))]
    for asset in matches:
        name = str(asset.get("name", ""))
        if name.endswith(".tar.gz"):
            tarball = asset
        elif name.endswith(".sha256"):
            checksum = asset
    return tarball, checksum, matches


def _download(url: str, target: Path) -> None:
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=65536):
                if chunk:
                    handle.write(chunk)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _extract_packs(tarball: Path, target: Path) -> Path:
    with tarfile.open(tarball, "r:gz") as archive:
        archive.extractall(target)
    if (target / "packs").exists():
        return target / "packs"
    candidates = list(target.rglob("packs"))
    if candidates:
        return candidates[0]
    raise SystemExit("downloaded tarball does not contain a packs/ directory")


def _print_token_status(token: dict[str, Any]) -> None:
    print(f"token_status: {token.get('status')}")
    print(f"token_channel: {token.get('channel')}")
    print(f"token_expires_at: {token.get('expires_at')}")


def cmd_install(args: argparse.Namespace) -> int:
    message = _install_codex_agent(args.dry_run) if args.agent == "codex" else _install_json_agent(args.agent, args.dry_run)
    print(message)
    if args.dry_run:
        print(f"[dry-run] data_dir would be {paths.data_root()}")
        print("[dry-run] would bootstrap user data and create/update trial supporter token")
        return 0
    paths.ensure_user_data()
    token = supporter.ensure_trial_token()
    print(f"data_dir: {paths.data_root()}")
    print(f"trial_token_status: {token.get('status')}")
    print("next: run `polaris demo` then `polaris on --agent %s`" % args.agent)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    del args
    paths.ensure_user_data()
    token = supporter.token_state()
    print(f"data_dir: {paths.data_root()}")
    print(f"configured_agents: {json.dumps(_configured_agents(), indent=2)}")
    _print_token_status(token)
    print(f"current_channel: {supporter.current_channel(token)}")
    counts = Counter(pattern.tier for pattern in load_index())
    print(f"loaded_patterns_by_tier: {json.dumps(dict(counts), sort_keys=True)}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    del args
    paths.ensure_user_data()
    error_text = "ModuleNotFoundError: No module named 'requests'"
    print("before:")
    print(error_text)
    hits = match(error_text, ecosystem="python", limit=1)
    print("after:")
    if not hits:
        print("no Polaris match found")
        return 1
    hit = hits[0]
    print(json.dumps({
        "id": hit.pattern_id,
        "tier": hit.tier,
        "fix": hit.fix_path.get("description") or hit.fix_path.get("fix_command"),
        "verify": hit.shortest_verification.get("command", ""),
    }, indent=2))
    return 0


def cmd_on(args: argparse.Namespace) -> int:
    path = _update_rules(args.agent, True, Path.cwd())
    print(f"enabled Polaris rule in {path}")
    return 0


def cmd_off(args: argparse.Namespace) -> int:
    path = _update_rules(args.agent, False, Path.cwd())
    print(f"removed Polaris rule from {path}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    token = supporter.token_state()
    channel = args.channel or supporter.current_channel(token)
    if channel == "fresh" and not supporter.fresh_allowed(token):
        print("fresh channel requires an active or trial supporter token", file=sys.stderr)
        return 1
    try:
        tarball, checksum, matches = _matching_assets(channel)
    except requests.RequestException as exc:
        if args.dry_run:
            print(f"channel: {channel}")
            print(f"- unable to query GitHub releases right now: {exc}")
            print(f"- expected asset: polaris-packs-{channel}-vX.Y.Z.tar.gz")
            print(f"- expected checksum: polaris-packs-{channel}-vX.Y.Z.sha256")
            return 0
        print(f"failed to query GitHub releases: {exc}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"channel: {channel}")
        if matches:
            for asset in matches:
                print(f"- {asset.get('name')} ({asset.get('browser_download_url')})")
        else:
            print(f"- no published assets found; expected: polaris-packs-{channel}-vX.Y.Z.tar.gz")
            print(f"- no published assets found; expected: polaris-packs-{channel}-vX.Y.Z.sha256")
        return 0
    if not tarball or not checksum:
        print(f"missing release assets for channel {channel}", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="polaris-update-") as tmpdir:
        tmp = Path(tmpdir)
        tar_path = tmp / str(tarball["name"])
        sha_path = tmp / str(checksum["name"])
        _download(str(tarball["browser_download_url"]), tar_path)
        _download(str(checksum["browser_download_url"]), sha_path)
        expected = sha_path.read_text().strip().split()[0]
        actual = _sha256(tar_path)
        if actual != expected:
            print("sha256 mismatch for downloaded packs tarball", file=sys.stderr)
            return 1
        extracted = _extract_packs(tar_path, tmp / "extract")
        current = paths.packs_root()
        backup = paths.data_root() / "packs.backup"
        if backup.exists():
            shutil.rmtree(backup)
        if current.exists():
            current.rename(backup)
        try:
            shutil.move(str(extracted), str(current))
        except Exception:
            if backup.exists():
                backup.rename(current)
            raise
        if backup.exists():
            shutil.rmtree(backup)
    print(f"updated packs channel={channel}")
    return 0


def cmd_activate(args: argparse.Namespace) -> int:
    ok, message = supporter.activate_license(args.key)
    print(message)
    return 0 if ok else 1


def cmd_supporter_stats(args: argparse.Namespace) -> int:
    del args
    paths.ensure_user_data()
    fp = _fingerprint()
    promoted_patterns = 0
    for shard in paths.community_packs_dir().rglob("*.json"):
        try:
            data = json.loads(shard.read_text())
        except json.JSONDecodeError:
            continue
        for rec in data.get("records", []):
            if rec.get("contributor_fingerprint") == fp:
                promoted_patterns += 1
    validations_written = 0
    validations_promoted = 0
    for journal in paths.validations_dir().glob("*.jsonl"):
        rows = [row for row in journal.read_text().splitlines() if row.strip()]
        for row in rows:
            try:
                payload = json.loads(row)
            except json.JSONDecodeError:
                continue
            if payload.get("validator_fingerprint") == fp:
                validations_written += 1
                if (paths.promoted_dir() / f"{payload.get('pattern_id')}.json").exists():
                    validations_promoted += 1
    print(f"fingerprint: {fp}")
    print(f"your_promoted_patterns: {promoted_patterns}")
    print(f"your_validations_written: {validations_written}")
    print(f"your_validations_that_reached_promote: {validations_promoted}")
    return 0


def cmd_serve_mcp(args: argparse.Namespace) -> int:
    del args
    adapter_server.main()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="polaris")
    sub = parser.add_subparsers(dest="cmd", required=True)

    install = sub.add_parser("install")
    install.add_argument("--agent", choices=["claude-code", "codex", "cursor"], required=True)
    install.add_argument("--dry-run", action="store_true")
    install.set_defaults(func=cmd_install)

    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)

    demo = sub.add_parser("demo")
    demo.set_defaults(func=cmd_demo)

    on = sub.add_parser("on")
    on.add_argument("--agent", choices=["claude-code", "codex", "cursor"], required=True)
    on.set_defaults(func=cmd_on)

    off = sub.add_parser("off")
    off.add_argument("--agent", choices=["claude-code", "codex", "cursor"], required=True)
    off.set_defaults(func=cmd_off)

    update = sub.add_parser("update")
    update.add_argument("--channel", choices=["stable", "fresh"])
    update.add_argument("--dry-run", action="store_true")
    update.set_defaults(func=cmd_update)

    activate = sub.add_parser("activate")
    activate.add_argument("key")
    activate.set_defaults(func=cmd_activate)

    supporter_stats = sub.add_parser("supporter-stats")
    supporter_stats.set_defaults(func=cmd_supporter_stats)

    submit = sub.add_parser("submit")
    submit.add_argument("file")
    submit.set_defaults(func=cmd_submit)

    confirm = sub.add_parser("confirm")
    confirm.add_argument("pattern_id")
    confirm.add_argument("--note", default="")
    confirm.set_defaults(func=cmd_confirm)

    reject = sub.add_parser("reject")
    reject.add_argument("pattern_id")
    reject.add_argument("--reason", default="")
    reject.set_defaults(func=cmd_reject)

    promote = sub.add_parser("promote")
    promote.add_argument("--verbose", action="store_true")
    promote.set_defaults(func=cmd_promote)

    serve = sub.add_parser("serve-mcp")
    serve.set_defaults(func=cmd_serve_mcp)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
