#!/usr/bin/env python3
"""Config loader tests — verify conf file is read and wired into runtime."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PARENT_DIR)

passed = 0
failed = 0


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name} — {detail}")


# ── Config loader basics ─────────────────────────────────────────────────────

from config import load_conf, get_int, DEFAULTS

# Load from nonexistent file → defaults
conf = load_conf("/tmp/nonexistent_trialogue_conf_xxxxx")
check("missing file: returns defaults", conf == DEFAULTS,
      f"got: {conf}")

# Load from real file
tmpdir = tempfile.mkdtemp(prefix="trialogue_conf_test_")
try:
    conf_path = os.path.join(tmpdir, "test.conf")
    with open(conf_path, "w") as f:
        f.write("# comment line\n")
        f.write("max_response_bytes=1048576\n")
        f.write("default_timeout=30\n")
        f.write("search_endpoint=https://search.example.com/v1\n")
        f.write("audit_mode=disabled\n")
        f.write("\n")  # blank line
        f.write("sanitizer_mode=permissive\n")

    conf = load_conf(conf_path)
    check("custom: max_response_bytes", conf["max_response_bytes"] == "1048576",
          f"got: {conf['max_response_bytes']}")
    check("custom: default_timeout", conf["default_timeout"] == "30",
          f"got: {conf['default_timeout']}")
    check("custom: search_endpoint", conf["search_endpoint"] == "https://search.example.com/v1",
          f"got: {conf['search_endpoint']}")
    check("custom: audit_mode", conf["audit_mode"] == "disabled",
          f"got: {conf['audit_mode']}")
    check("custom: sanitizer_mode", conf["sanitizer_mode"] == "permissive",
          f"got: {conf['sanitizer_mode']}")

    # Keys not in test file fall back to DEFAULTS
    # (test file sets audit_mode, max_response_bytes, default_timeout, search_endpoint, sanitizer_mode
    #  but does NOT set any unknown keys — verify DEFAULTS supplies them)
    from config import DEFAULTS
    for key in DEFAULTS:
        check(f"custom: default key '{key}' present", key in conf,
              f"key {key} missing from loaded conf")

    # get_int helper
    check("get_int: valid", get_int(conf, "max_response_bytes") == 1048576,
          f"got: {get_int(conf, 'max_response_bytes')}")
    check("get_int: default", get_int(conf, "nonexistent_key", 42) == 42,
          f"got: {get_int(conf, 'nonexistent_key', 42)}")

    # Env var override
    os.environ["TRIALOGUE_CONF"] = conf_path
    try:
        from config import load_conf as lc2
        conf2 = lc2()  # no path arg → should read TRIALOGUE_CONF
        check("env override: reads custom path", conf2["audit_mode"] == "disabled",
              f"got: {conf2['audit_mode']}")
    finally:
        del os.environ["TRIALOGUE_CONF"]

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)

# ── Config wired into pipeline ───────────────────────────────────────────────

# pipeline.py reads config at import time — verify it has the config values
import pipeline
check("pipeline: MAX_RESPONSE_BYTES from conf",
      isinstance(pipeline.MAX_RESPONSE_BYTES, int) and pipeline.MAX_RESPONSE_BYTES > 0,
      f"got: {pipeline.MAX_RESPONSE_BYTES}")
check("pipeline: DEFAULT_TIMEOUT from conf",
      isinstance(pipeline.DEFAULT_TIMEOUT, int) and pipeline.DEFAULT_TIMEOUT > 0,
      f"got: {pipeline.DEFAULT_TIMEOUT}")

# ── Summary ──────────────────────────────────────────────────────────────────

print(f"config_test: {passed}/{passed + failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
