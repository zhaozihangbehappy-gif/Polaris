#!/usr/bin/env python3
"""Trialogue v4 — Network egress control.

Manages iptables/nftables rules to restrict outbound HTTP/HTTPS traffic
so that only the trialogue pipeline process (running as a dedicated system
user `_trialogue`) can reach external hosts on ports 80/443.

Two modes:
  - kernel:       iptables owner match (requires root + _trialogue user)
  - pattern_only: no network-level enforcement, relies on hook pattern matching

Usage (called by `trialogue guard on --egress`):
    python3 egress.py enable   # create user + iptables rules
    python3 egress.py disable  # remove iptables rules (user preserved)
    python3 egress.py status   # report current egress mode
"""
from __future__ import annotations

import os
import subprocess
import sys

TRIALOGUE_USER = "_trialogue"

# iptables chain name to keep rules grouped
CHAIN_NAME = "TRIALOGUE_EGRESS"

# Ports to control (base set — proxy ports added dynamically)
CONTROLLED_PORTS = [80, 443]


def _detect_proxy_ports() -> list[int]:
    """Detect HTTP/HTTPS proxy ports from environment variables.

    Under sudo, env vars are stripped. We recover them from the parent
    process's environment via /proc/<ppid>/environ.
    """
    proxy_vars = ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY")
    env_values: list[str] = []

    # Try current environment first
    for var in proxy_vars:
        val = os.environ.get(var, "")
        if val:
            env_values.append(val)

    # Under sudo with no proxy vars, read from parent process environ
    if not env_values and os.environ.get("SUDO_USER"):
        try:
            ppid = os.getppid()
            with open(f"/proc/{ppid}/environ", "r") as f:
                parent_env = f.read()
            for entry in parent_env.split("\0"):
                if "=" in entry:
                    key, _, val = entry.partition("=")
                    if key in proxy_vars and val:
                        env_values.append(val)
                        # Also set in current env so _trialogue inherits it
                        os.environ[key] = val
        except (OSError, PermissionError):
            pass

    ports = set()
    from urllib.parse import urlparse
    for val in env_values:
        try:
            parsed = urlparse(val)
            if parsed.port and parsed.port not in (80, 443):
                ports.add(parsed.port)
        except Exception:
            pass
    return sorted(ports)


def get_controlled_ports() -> list[int]:
    """Return full list of ports to control, including detected proxy ports."""
    proxy_ports = _detect_proxy_ports()
    all_ports = list(CONTROLLED_PORTS)
    for p in proxy_ports:
        if p not in all_ports:
            all_ports.append(p)
    return all_ports


def _has_root() -> bool:
    return os.geteuid() == 0


def _user_exists(username: str) -> bool:
    try:
        result = subprocess.run(
            ["id", username], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def _get_uid(username: str) -> int | None:
    try:
        result = subprocess.run(
            ["id", "-u", username], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return int(result.stdout.strip())
    except Exception:
        pass
    return None


SUDOERS_FILE = "/etc/sudoers.d/trialogue-guard"


def ensure_sudoers() -> tuple[bool, str]:
    """Ensure a NOPASSWD sudoers rule exists so any user can run MCP as _trialogue.

    Writes /etc/sudoers.d/trialogue-guard with:
        ALL ALL=(TRIALOGUE_USER) NOPASSWD: /usr/bin/python3 <mcp-server.py path>

    This is required because Claude Code launches the MCP server command directly,
    and cannot provide a password for sudo.

    Returns (success, message).
    """
    if not _has_root():
        return False, "Root required to write sudoers rule"

    if not _user_exists(TRIALOGUE_USER):
        return False, f"User {TRIALOGUE_USER} does not exist"

    import sys as _sys
    mcp_server_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "mcp-server.py"
    )
    python_path = _sys.executable

    rule = (
        f"# Trialogue v4 — allow any user to run MCP server as {TRIALOGUE_USER}\n"
        f"ALL ALL=({TRIALOGUE_USER}) NOPASSWD: {python_path} {mcp_server_path}\n"
    )

    try:
        # Validate with visudo -c before writing
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sudoers", delete=False) as tf:
            tf.write(rule)
            tf_path = tf.name

        check = subprocess.run(
            ["visudo", "-c", "-f", tf_path],
            capture_output=True, text=True, timeout=5,
        )
        os.unlink(tf_path)

        if check.returncode != 0:
            return False, f"sudoers rule validation failed: {check.stderr.strip()}"

        # Write the real file
        with open(SUDOERS_FILE, "w") as f:
            f.write(rule)
        os.chmod(SUDOERS_FILE, 0o440)

        return True, f"sudoers rule written to {SUDOERS_FILE}"
    except Exception as e:
        return False, f"Failed to write sudoers rule: {e}"


def remove_sudoers() -> tuple[bool, str]:
    """Remove the trialogue sudoers rule. Returns (success, message)."""
    if os.path.exists(SUDOERS_FILE):
        try:
            os.unlink(SUDOERS_FILE)
            return True, f"Removed {SUDOERS_FILE}"
        except OSError as e:
            return False, f"Failed to remove {SUDOERS_FILE}: {e}"
    return True, "No sudoers rule to remove"


def _iptables_available() -> bool:
    try:
        result = subprocess.run(
            ["iptables", "--version"], capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def _install_iptables() -> tuple[bool, str]:
    """Attempt to install iptables if missing. Requires root.

    Returns (success, message).
    """
    if _iptables_available():
        return True, "iptables already installed"

    if not _has_root():
        return False, "iptables not installed and no root to install it"

    # Detect package manager and install
    for cmd in [
        ["apt-get", "install", "-y", "iptables"],       # Debian/Ubuntu
        ["yum", "install", "-y", "iptables"],            # RHEL/CentOS
        ["dnf", "install", "-y", "iptables"],            # Fedora
        ["apk", "add", "iptables"],                      # Alpine
        ["pacman", "-S", "--noconfirm", "iptables"],     # Arch
    ]:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and _iptables_available():
                return True, f"Installed iptables via {cmd[0]}"
        except FileNotFoundError:
            continue

    return False, "Could not install iptables — no supported package manager found"


def _chain_exists() -> bool:
    try:
        result = subprocess.run(
            ["iptables", "-n", "-L", CHAIN_NAME],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0
    except Exception:
        return False


def create_user() -> tuple[bool, str]:
    """Create the _trialogue system user if it doesn't exist.

    Returns (success, message).
    """
    if _user_exists(TRIALOGUE_USER):
        return True, f"User {TRIALOGUE_USER} already exists"

    if not _has_root():
        return False, "Root required to create system user"

    try:
        result = subprocess.run(
            ["useradd", "--system", "--no-create-home", "--shell", "/usr/sbin/nologin",
             TRIALOGUE_USER],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return True, f"Created system user {TRIALOGUE_USER}"
        return False, f"useradd failed: {result.stderr.strip()}"
    except FileNotFoundError:
        # Try adduser (Alpine/busybox)
        try:
            result = subprocess.run(
                ["adduser", "-S", "-D", "-H", "-s", "/usr/sbin/nologin",
                 TRIALOGUE_USER],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                return True, f"Created system user {TRIALOGUE_USER} (adduser)"
            return False, f"adduser failed: {result.stderr.strip()}"
        except FileNotFoundError:
            return False, "Neither useradd nor adduser found"


def enable_egress() -> tuple[str, str]:
    """Enable network egress control.

    Returns (mode, message) where mode is "kernel" or "pattern_only".
    """
    if not _has_root():
        return "pattern_only", (
            "Network egress control requires root — "
            "falling back to pattern matching only"
        )

    if not _iptables_available():
        print("[trialogue-guard] iptables not found — attempting to install...")
        ok, msg = _install_iptables()
        if not ok:
            return "pattern_only", (
                f"iptables not available and auto-install failed: {msg} — "
                "falling back to pattern matching only"
            )
        print(f"[trialogue-guard] {msg}")

    # Step 0b: Ensure xt_owner kernel module is loaded (needed for --uid-owner match)
    subprocess.run(
        ["modprobe", "xt_owner"],
        capture_output=True, text=True, timeout=5,
    )
    # Not fatal if this fails — some kernels have it built-in. We'll catch
    # the failure when the actual iptables rule with -m owner fails.

    # Step 1: Ensure user exists
    ok, msg = create_user()
    if not ok:
        return "pattern_only", f"Cannot create trialogue user: {msg}"

    uid = _get_uid(TRIALOGUE_USER)
    if uid is None:
        return "pattern_only", f"Cannot determine UID for {TRIALOGUE_USER}"

    # All iptables commands below are checked for success.
    # If any fail, we roll back and fall back to pattern_only.
    errors: list[str] = []

    def _ipt(*args: str) -> bool:
        """Run iptables command, return True on success, record errors."""
        result = subprocess.run(
            ["iptables"] + list(args),
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            errors.append(f"iptables {' '.join(args)}: {result.stderr.strip()}")
            return False
        return True

    # Step 2: Create dedicated chain (idempotent)
    if not _chain_exists():
        _ipt("-N", CHAIN_NAME)

    if not _chain_exists():
        return "pattern_only", f"Failed to create iptables chain: {'; '.join(errors)}"

    # Step 3: Flush any existing rules in our chain
    _ipt("-F", CHAIN_NAME)

    # Step 4: Add rules to our chain
    ports = get_controlled_ports()
    if len(ports) > len(CONTROLLED_PORTS):
        proxy_extra = [p for p in ports if p not in CONTROLLED_PORTS]
        print(f"[trialogue-guard] Detected proxy ports: {proxy_extra} — adding to egress control")
    # Allow _trialogue user outbound on controlled ports
    for port in ports:
        _ipt("-A", CHAIN_NAME,
             "-p", "tcp", "--dport", str(port),
             "-m", "owner", "--uid-owner", str(uid),
             "-j", "ACCEPT")
    # Allow localhost (any user) on controlled ports
    for port in ports:
        _ipt("-A", CHAIN_NAME,
             "-p", "tcp", "--dport", str(port),
             "-d", "127.0.0.0/8",
             "-j", "ACCEPT")
    # Reject all other outbound on controlled ports
    for port in ports:
        _ipt("-A", CHAIN_NAME,
             "-p", "tcp", "--dport", str(port),
             "-j", "REJECT", "--reject-with", "tcp-reset")

    # Check if any rule additions failed
    if errors:
        # Roll back: flush and delete chain
        subprocess.run(["iptables", "-F", CHAIN_NAME],
                       capture_output=True, text=True, timeout=5)
        subprocess.run(["iptables", "-X", CHAIN_NAME],
                       capture_output=True, text=True, timeout=5)
        return "pattern_only", (
            f"iptables rules failed to install — rolled back: {'; '.join(errors)}"
        )

    # Step 5: Jump from OUTPUT to our chain (idempotent — check first)
    check = subprocess.run(
        ["iptables", "-C", "OUTPUT", "-j", CHAIN_NAME],
        capture_output=True, text=True, timeout=5,
    )
    if check.returncode != 0:
        if not _ipt("-I", "OUTPUT", "1", "-j", CHAIN_NAME):
            # Roll back
            subprocess.run(["iptables", "-F", CHAIN_NAME],
                           capture_output=True, text=True, timeout=5)
            subprocess.run(["iptables", "-X", CHAIN_NAME],
                           capture_output=True, text=True, timeout=5)
            return "pattern_only", (
                f"Failed to insert OUTPUT jump: {'; '.join(errors)}"
            )

    # Step 6: Verify rules are actually in place
    verify = subprocess.run(
        ["iptables", "-n", "-L", CHAIN_NAME],
        capture_output=True, text=True, timeout=5,
    )
    if verify.returncode != 0 or str(uid) not in verify.stdout:
        # Rules didn't stick
        subprocess.run(["iptables", "-D", "OUTPUT", "-j", CHAIN_NAME],
                       capture_output=True, text=True, timeout=5)
        subprocess.run(["iptables", "-F", CHAIN_NAME],
                       capture_output=True, text=True, timeout=5)
        subprocess.run(["iptables", "-X", CHAIN_NAME],
                       capture_output=True, text=True, timeout=5)
        return "pattern_only", (
            f"iptables rules did not verify — rolled back. "
            f"Verify output: {verify.stdout[:200]}"
        )

    return "kernel", (
        f"Egress control enabled: only {TRIALOGUE_USER} (uid={uid}) "
        f"can reach ports {ports}"
    )


def disable_egress() -> tuple[bool, str]:
    """Remove egress control iptables rules.

    Returns (success, message). Does NOT remove the _trialogue user.
    """
    if not _has_root():
        return False, "Root required to remove iptables rules"

    if not _iptables_available():
        return True, "iptables not available — nothing to remove"

    # Remove jump from OUTPUT
    subprocess.run(
        ["iptables", "-D", "OUTPUT", "-j", CHAIN_NAME],
        capture_output=True, text=True, timeout=5,
    )

    # Flush and delete our chain
    if _chain_exists():
        subprocess.run(
            ["iptables", "-F", CHAIN_NAME],
            capture_output=True, text=True, timeout=5,
        )
        subprocess.run(
            ["iptables", "-X", CHAIN_NAME],
            capture_output=True, text=True, timeout=5,
        )

    # Remove sudoers rule
    remove_sudoers()

    return True, "Egress control disabled (user preserved for reuse)"


def get_status() -> dict[str, str]:
    """Report current egress control status."""
    result: dict[str, str] = {}

    result["user_exists"] = "yes" if _user_exists(TRIALOGUE_USER) else "no"
    uid = _get_uid(TRIALOGUE_USER)
    result["user_uid"] = str(uid) if uid is not None else "n/a"
    result["has_root"] = "yes" if _has_root() else "no"
    result["iptables_available"] = "yes" if _iptables_available() else "no"
    result["chain_exists"] = "yes" if _chain_exists() else "no"

    result["sudoers_rule"] = "yes" if os.path.exists(SUDOERS_FILE) else "no"

    if (result["chain_exists"] == "yes" and result["user_exists"] == "yes"
            and result["sudoers_rule"] == "yes"):
        result["egress_mode"] = "kernel"
    else:
        result["egress_mode"] = "pattern_only"

    return result


def mcp_command_prefix() -> list[str]:
    """Return the command prefix for running MCP server as _trialogue user.

    If _trialogue user exists, returns ["sudo", "-u", "_trialogue", ...].
    Otherwise returns empty list (run as current user).
    """
    if _user_exists(TRIALOGUE_USER):
        return ["sudo", "-u", TRIALOGUE_USER]
    return []


# ── CLI ──────────────────────────────────────────────────────────────────────

def _cli_main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("enable", "disable", "status"):
        print("Usage: egress.py enable|disable|status", file=sys.stderr)
        return 2

    cmd = sys.argv[1]

    if cmd == "enable":
        mode, msg = enable_egress()
        print(f"egress: {mode} — {msg}")
        return 0 if mode == "kernel" else 1

    if cmd == "disable":
        ok, msg = disable_egress()
        print(f"egress: {msg}")
        return 0 if ok else 1

    if cmd == "status":
        status = get_status()
        for k, v in status.items():
            print(f"  {k}: {v}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(_cli_main())
