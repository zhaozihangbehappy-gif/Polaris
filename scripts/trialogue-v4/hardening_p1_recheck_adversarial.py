#!/usr/bin/env python3
"""P1-1 Version Recheck 专项对抗测试"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from hardening import (
    evaluate_version_gate,
    evaluate_version_recheck,
    load_hardening_settings,
    snapshot_runner_version,
)

FAIL_COUNT = 0
PASS_COUNT = 0


def check(name: str, condition: bool, detail: str = ""):
    global FAIL_COUNT, PASS_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  ✓ {name}")
    else:
        FAIL_COUNT += 1
        print(f"  ✗ FAIL: {name} — {detail}")


def make_conf(tmp: Path, **kw) -> Path:
    conf = tmp / "recheck.conf"
    lines = [
        "HARDENING_TRANSCRIPT_SANITIZER=strict",
        f"HARDENING_SANITIZER_PATTERNS={tmp / 'p.json'}",
        f"HARDENING_VERSION_GATE={kw.get('gate', 'enforce')}",
        f"HARDENING_VERSION_GATE_RECHECK={kw.get('recheck', 'enforce')}",
        f"HARDENING_VERSION_ALLOWLIST={tmp / 'al.json'}",
        "HARDENING_OPERATION_LOCKS=enabled",
        "HARDENING_LOCK_TIMEOUT_SEC=1",
        f"HARDENING_VERSION_RECHECK_FAST_INTERVAL_SEC={kw.get('fast', '10')}",
        f"HARDENING_VERSION_RECHECK_FULL_INTERVAL_SEC={kw.get('full', '60')}",
    ]
    conf.write_text("\n".join(lines), encoding="utf-8")
    (tmp / "p.json").write_text('{"block_wrappers":[],"single_line_headers":[]}')
    return conf


def make_allowlist(tmp: Path, claude_hashes=None, codex_hashes=None):
    al = tmp / "al.json"
    al.write_text(json.dumps({
        "policy": "enforce",
        "runners": {
            "claude": {"versions": [], "hashes": claude_hashes or []},
            "codex": {"versions": [], "hashes": codex_hashes or []},
        },
    }))


def make_snap(path="", sha="", version="v1", exists=True, size=100, mtime_ns=1000000000, t=None):
    t = t or time.time()
    return {
        "binary_path": path,
        "binary_exists": exists,
        "binary_sha256": sha,
        "cli_version": version,
        "binary_size": size,
        "binary_mtime_ns": mtime_ns,
        "checked_at": t,
        "full_hash_at": t,
        "snapshot_mode": "full",
    }


def test_recheck_four_outcomes():
    """验证 recheck 的 4 种 outcome"""
    print("\n═══ 1. Recheck 四种 Outcome ═══")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_allowlist(tmp, claude_hashes=["hash_a", "hash_b"])
        conf = make_conf(tmp, gate="enforce", recheck="enforce")
        settings = load_hardening_settings(str(conf))

        startup = make_snap(path="/bin/claude", sha="hash_a", version="v1")

        # match — 没有变化
        r = evaluate_version_recheck("claude", startup, startup, settings=settings)
        check("match: 完全相同", r["result"] == "match" and r["allowed"])

        # changed-but-allowed — hash 变了但新 hash 也在 allowlist 里
        inv = make_snap(path="/bin/claude", sha="hash_b", version="v2")
        r = evaluate_version_recheck("claude", startup, inv, settings=settings)
        check("changed-but-allowed", r["result"] == "changed-but-allowed" and r["allowed"],
              f"result={r['result']} allowed={r['allowed']}")

        # changed-and-unapproved — hash 变了且不在 allowlist
        inv = make_snap(path="/bin/claude", sha="hash_evil", version="v3")
        r = evaluate_version_recheck("claude", startup, inv, settings=settings)
        check("changed-and-unapproved (enforce)", r["result"] == "changed-and-unapproved" and not r["allowed"],
              f"result={r['result']} allowed={r['allowed']}")

        # missing — 二进制消失了
        inv = make_snap(path="/bin/claude", sha="", version="missing", exists=False)
        r = evaluate_version_recheck("claude", startup, inv, settings=settings)
        check("missing", r["result"] == "missing" and not r["allowed"],
              f"result={r['result']} allowed={r['allowed']}")


def test_recheck_policy_levels():
    """验证 recheck 的三档 policy"""
    print("\n═══ 2. Recheck Policy 三档 ═══")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_allowlist(tmp, claude_hashes=["hash_a"])
        startup = make_snap(path="/bin/claude", sha="hash_a")
        inv_bad = make_snap(path="/bin/claude", sha="hash_evil")

        # enforce — 拦截
        conf = make_conf(tmp, gate="enforce", recheck="enforce")
        settings = load_hardening_settings(str(conf))
        r = evaluate_version_recheck("claude", startup, inv_bad, settings=settings)
        check("enforce 拦截", not r["allowed"])

        # warn — 放行
        conf = make_conf(tmp, gate="warn", recheck="warn")
        settings = load_hardening_settings(str(conf))
        r = evaluate_version_recheck("claude", startup, inv_bad, settings=settings)
        check("warn 放行", r["allowed"] and r["result"] == "changed-and-unapproved")

        # disabled — 放行 + result=disabled
        conf = make_conf(tmp, gate="disabled", recheck="disabled")
        settings = load_hardening_settings(str(conf))
        r = evaluate_version_recheck("claude", startup, inv_bad, settings=settings)
        check("disabled 放行", r["allowed"] and r["result"] == "disabled")


def test_recheck_policy_coupling():
    """验证 recheck 不得弱于 gate 的耦合规则"""
    print("\n═══ 3. Policy 耦合规则 ═══")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_allowlist(tmp, claude_hashes=[])
        (tmp / "p.json").write_text('{"block_wrappers":[],"single_line_headers":[]}')

        # gate=enforce, recheck=disabled → 应被提升到 enforce
        conf = make_conf(tmp, gate="enforce", recheck="disabled")
        settings = load_hardening_settings(str(conf))
        check("enforce+disabled → recheck 提升", settings.version_gate_recheck == "enforce",
              f"got: {settings.version_gate_recheck}")

        # gate=warn, recheck=disabled → 应被提升到 warn
        conf = make_conf(tmp, gate="warn", recheck="disabled")
        settings = load_hardening_settings(str(conf))
        check("warn+disabled → recheck 提升", settings.version_gate_recheck == "warn",
              f"got: {settings.version_gate_recheck}")

        # gate=warn, recheck=enforce → 允许 recheck 更严格
        conf = make_conf(tmp, gate="warn", recheck="enforce")
        settings = load_hardening_settings(str(conf))
        check("warn+enforce → recheck 可更严格", settings.version_gate_recheck == "enforce")

        # gate=disabled, recheck=enforce → 允许
        conf = make_conf(tmp, gate="disabled", recheck="enforce")
        settings = load_hardening_settings(str(conf))
        check("disabled+enforce → 允许", settings.version_gate_recheck == "enforce")


def test_stat_shortcircuit():
    """验证 mtime/size 短路逻辑"""
    print("\n═══ 4. Stat 短路 ═══")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        fake_bin = tmp / "claude"
        fake_bin.write_bytes(b"binary content v1")
        fake_bin.chmod(0o755)
        h = hashlib.sha256(fake_bin.read_bytes()).hexdigest()
        make_allowlist(tmp, claude_hashes=[h])
        # 写 conf 指向真实二进制
        conf = tmp / "recheck.conf"
        conf.write_text("\n".join([
            "HARDENING_TRANSCRIPT_SANITIZER=strict",
            f"HARDENING_SANITIZER_PATTERNS={tmp / 'p.json'}",
            "HARDENING_VERSION_GATE=enforce",
            "HARDENING_VERSION_GATE_RECHECK=enforce",
            f"HARDENING_VERSION_ALLOWLIST={tmp / 'al.json'}",
            "HARDENING_OPERATION_LOCKS=enabled",
            f"CLAUDE_BIN={fake_bin}",
            "HARDENING_VERSION_RECHECK_FAST_INTERVAL_SEC=9999",
            "HARDENING_VERSION_RECHECK_FULL_INTERVAL_SEC=9999",
        ]))
        (tmp / "p.json").write_text('{"block_wrappers":[],"single_line_headers":[]}')

        settings = load_hardening_settings(str(conf))

        # 首次 full snapshot
        snap1 = snapshot_runner_version("claude", str(conf), settings=settings)
        check("首次 full snapshot", snap1["snapshot_mode"] == "full" and snap1["binary_sha256"] == h)

        # 不改文件，紧接着再次 snapshot — 应走 stat_only
        snap2 = snapshot_runner_version("claude", str(conf), settings=settings, previous_snapshot=snap1)
        check("stat 未变 → stat_only 短路", snap2["snapshot_mode"] == "stat_only",
              f"mode={snap2['snapshot_mode']}")
        check("stat_only 复用旧 hash", snap2["binary_sha256"] == h)

        # 改文件内容（mtime/size 变化）→ 强制 full
        fake_bin.write_bytes(b"binary content v2 with extra bytes")
        snap3 = snapshot_runner_version("claude", str(conf), settings=settings, previous_snapshot=snap2)
        check("文件变更 → full snapshot", snap3["snapshot_mode"] == "full",
              f"mode={snap3['snapshot_mode']}")
        new_h = hashlib.sha256(b"binary content v2 with extra bytes").hexdigest()
        check("full snapshot 得到新 hash", snap3["binary_sha256"] == new_h,
              f"got: {snap3['binary_sha256']}")

        # force_full 参数
        snap4 = snapshot_runner_version("claude", str(conf), settings=settings, previous_snapshot=snap3, force_full=True)
        check("force_full 强制完整快照", snap4["snapshot_mode"] == "full")


def test_changed_fields_tracking():
    """验证 changed_fields 正确追踪变化的维度"""
    print("\n═══ 5. Changed Fields 追踪 ═══")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_allowlist(tmp, claude_hashes=[])
        conf = make_conf(tmp, gate="enforce", recheck="warn")
        settings = load_hardening_settings(str(conf))

        startup = make_snap(path="/bin/claude", sha="aaa", version="v1")

        # 只 hash 变
        inv = make_snap(path="/bin/claude", sha="bbb", version="v1")
        r = evaluate_version_recheck("claude", startup, inv, settings=settings)
        check("只 hash 变", "binary_sha256" in r["changed_fields"] and "cli_version" not in r["changed_fields"],
              f"changed: {r['changed_fields']}")

        # 只 version 变
        inv = make_snap(path="/bin/claude", sha="aaa", version="v2")
        r = evaluate_version_recheck("claude", startup, inv, settings=settings)
        check("只 version 变", "cli_version" in r["changed_fields"] and "binary_sha256" not in r["changed_fields"],
              f"changed: {r['changed_fields']}")

        # 路径变
        inv = make_snap(path="/bin/claude-new", sha="aaa", version="v1")
        r = evaluate_version_recheck("claude", startup, inv, settings=settings)
        check("路径变", "binary_path" in r["changed_fields"],
              f"changed: {r['changed_fields']}")

        # 全变
        inv = make_snap(path="/bin/x", sha="zzz", version="v99", exists=True)
        r = evaluate_version_recheck("claude", startup, inv, settings=settings)
        check("全变", len(r["changed_fields"]) >= 3,
              f"changed: {r['changed_fields']}")

        # 什么都没变
        r = evaluate_version_recheck("claude", startup, startup, settings=settings)
        check("无变化", r["changed_fields"] == [] and r["result"] == "match")


def test_broker_only_recheck():
    """验证 recheck 元数据不进 agent context"""
    print("\n═══ 6. Broker-Only (Recheck) ═══")

    # recheck 结果通过 env vars 传给 launcher → _audit.py
    # 不应出现在 agent 的 --message 里
    # 检查 chat.py 里 version_meta 只通过 env vars 传递
    chat_py = Path("/home/administrator/.openclaw/workspace/scripts/trialogue-v3/chat.py")
    src = chat_py.read_text(encoding="utf-8")

    # 找 call_launcher 和 call_launcher_stream 函数
    import re
    # startup_snapshot / invocation_snapshot 只应出现在 env[...] = 赋值里，不在 message 构造里
    # message 变量名在 call_launcher 里是参数 message
    # 确认 version_meta 的使用只在 env 赋值段
    env_uses = re.findall(r'env\["TRIALOGUE_VERSION_(?:STARTUP|INVOCATION)[^"]*"\]', src)
    check(f"version snapshot 通过 env 传递 ({len(env_uses)} 处)", len(env_uses) >= 8,
          f"只找到 {len(env_uses)} 处 env 赋值")

    # 确认 message 参数里不拼接 version/recheck 信息
    # 搜索 injected_message 或 message 附近是否有 version_meta/recheck/snapshot
    message_lines = [line for line in src.split("\n")
                     if ("injected_message" in line or "wrapped_message" in line)
                     and ("version" in line.lower() or "recheck" in line.lower() or "snapshot" in line.lower())]
    check("message 构造不含 version/recheck", len(message_lines) == 0,
          f"可疑行: {message_lines}")


def test_config_defaults():
    """验证 recheck 配置默认值和边界"""
    print("\n═══ 7. 配置默认值和边界 ═══")

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        make_allowlist(tmp)
        (tmp / "p.json").write_text('{"block_wrappers":[],"single_line_headers":[]}')

        # 不指定 recheck → 默认跟 gate 一致
        conf = tmp / "recheck.conf"
        conf.write_text("\n".join([
            "HARDENING_VERSION_GATE=warn",
            f"HARDENING_VERSION_ALLOWLIST={tmp / 'al.json'}",
            f"HARDENING_SANITIZER_PATTERNS={tmp / 'p.json'}",
        ]))
        settings = load_hardening_settings(str(conf))
        check("recheck 默认跟 gate", settings.version_gate_recheck == "warn",
              f"got: {settings.version_gate_recheck}")

        # fast/full interval 默认值
        check("fast interval 默认 10s", settings.version_recheck_fast_interval_sec == 10.0,
              f"got: {settings.version_recheck_fast_interval_sec}")
        check("full interval 默认 60s", settings.version_recheck_full_interval_sec == 60.0,
              f"got: {settings.version_recheck_full_interval_sec}")

        # 负数 interval → 回退默认
        conf.write_text("\n".join([
            "HARDENING_VERSION_GATE=warn",
            f"HARDENING_VERSION_ALLOWLIST={tmp / 'al.json'}",
            f"HARDENING_SANITIZER_PATTERNS={tmp / 'p.json'}",
            "HARDENING_VERSION_RECHECK_FAST_INTERVAL_SEC=-5",
            "HARDENING_VERSION_RECHECK_FULL_INTERVAL_SEC=0",
        ]))
        settings = load_hardening_settings(str(conf))
        check("负数 fast interval → 默认", settings.version_recheck_fast_interval_sec == 10.0,
              f"got: {settings.version_recheck_fast_interval_sec}")
        check("零 full interval → 默认", settings.version_recheck_full_interval_sec == 60.0,
              f"got: {settings.version_recheck_full_interval_sec}")


def main():
    test_recheck_four_outcomes()
    test_recheck_policy_levels()
    test_recheck_policy_coupling()
    test_stat_shortcircuit()
    test_changed_fields_tracking()
    test_broker_only_recheck()
    test_config_defaults()

    print(f"\n{'═' * 50}")
    print(f"通过: {PASS_COUNT}  失败: {FAIL_COUNT}")
    if FAIL_COUNT:
        print("⚠ 存在问题")
    else:
        print("P1-1 recheck 全部通过")
    print(f"{'═' * 50}")
    return 1 if FAIL_COUNT else 0


if __name__ == "__main__":
    raise SystemExit(main())
