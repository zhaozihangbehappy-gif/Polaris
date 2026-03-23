#!/usr/bin/env python3
"""
P1-2/3/4 敌对审查测试
覆盖: 摘要链篡改、锚点签名伪造、验证器绕过、
      atomic_write 竞态、crash recovery 状态机、
      端口注册表竞态与绕过
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import tempfile
import threading
import time
from pathlib import Path

from hardening import (
    SUMMARY_CHAIN_GENESIS_SHA256,
    PortReservationRegistry,
    append_jsonl,
    append_summary_chain,
    atomic_write_json,
    build_turn_summary,
    export_anchor_bundle,
    read_json_file,
    verify_summary_chain,
)


PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✓ {name}")
    else:
        FAILED += 1
        extra = f" — {detail}" if detail else ""
        print(f"  ✗ {name}{extra}")


def _make_record(**overrides: object) -> dict:
    base = {
        "timestamp": "2026-03-23T00:00:00Z",
        "rid": "rid-adv",
        "nonce": "nonce-adv",
        "target": "claude",
        "target_name": "meeting",
        "target_source": "default",
        "target_path": "",
        "mode": "launcher_generated",
        "session_id": "sess-adv",
        "session_confirmed": True,
        "confirmation_method": "claude_session_file",
        "confirmation": {"turn_id": "turn-adv", "thread_id": "thread-adv"},
        "exit_code": 0,
        "binary_path": "/bin/claude",
        "binary_sha256": "aaa",
        "cli_version": "claude 1.0",
        "version_gate_policy": "warn",
        "version_gate_allowed": True,
        "version_gate_reason": "",
        "version_recheck_policy": "warn",
        "version_recheck_allowed": True,
        "version_recheck_result": "match",
        "version_recheck_reason": "",
        "message_body": "hello",
        "stdout": "reply",
        "stderr": "",
        "raw_event_log_path": "",
        "room_state_path": "",
    }
    base.update(overrides)
    return base


# ══════════════════════════════════════════════════════
# A. 摘要链篡改攻击
# ══════════════════════════════════════════════════════
def test_summary_chain_tampering() -> None:
    print("\n═══ A. 摘要链篡改攻击 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        chain_dir = str(Path(tmp) / "chain")
        anchor_dir = str(Path(tmp) / "anchor")
        key_path = str(Path(tmp) / "key")
        Path(key_path).write_text("secret-key", encoding="utf-8")
        os.chmod(key_path, 0o600)

        # 写两条正常记录
        r1 = _make_record(rid="r1", message_body="m1")
        r2 = _make_record(rid="r2", message_body="m2")
        c1 = append_summary_chain(chain_dir, r1, room_id="room-t", source_mode="test")
        export_anchor_bundle(anchor_dir, key_path, c1, policy="async")
        c2 = append_summary_chain(chain_dir, r2, room_id="room-t", source_mode="test")
        export_anchor_bundle(anchor_dir, key_path, c2, policy="async")

        # 验证正常通过
        ok_result = verify_summary_chain(
            os.path.join(chain_dir, "room-t.jsonl"),
            anchor_dir=anchor_dir,
            anchor_key_path=key_path,
        )
        check("正常链验证通过", ok_result["ok"] is True)

        # 篡改攻击 1: 修改 message_body_sha256 后验证
        chain_path = os.path.join(chain_dir, "room-t.jsonl")
        lines = Path(chain_path).read_text(encoding="utf-8").strip().split("\n")
        entry2 = json.loads(lines[1])
        entry2["summary"]["message_body_sha256"] = "0" * 64
        lines[1] = json.dumps(entry2, ensure_ascii=False)
        Path(chain_path).write_text("\n".join(lines) + "\n", encoding="utf-8")

        tamper1 = verify_summary_chain(
            chain_path,
            anchor_dir=anchor_dir,
            anchor_key_path=key_path,
        )
        check("篡改 summary 字段 → 验证失败", tamper1["ok"] is False, tamper1.get("reason", ""))

        # 篡改攻击 2: 修改 prev_summary_sha256 断链
        lines = Path(chain_path).read_text(encoding="utf-8").strip().split("\n")
        # 恢复 entry2 但改 prev hash
        c2_fresh = append_summary_chain(chain_dir + "-fresh", _make_record(rid="r2", message_body="m2"), room_id="room-t", source_mode="test")
        chain_path2 = os.path.join(chain_dir, "room-t.jsonl")
        entry2_obj = json.loads(lines[1])
        entry2_obj["prev_summary_sha256"] = "deadbeef" * 8
        lines[1] = json.dumps(entry2_obj, ensure_ascii=False)
        Path(chain_path2).write_text("\n".join(lines) + "\n", encoding="utf-8")

        tamper2 = verify_summary_chain(chain_path2)
        check("断链 prev_hash → 验证失败", tamper2["ok"] is False and "prev hash" in tamper2.get("reason", ""))

        # 篡改攻击 3: genesis hash 是确定性种子
        expected_genesis = hashlib.sha256(b"TRIALOGUE_V3_SUMMARY_CHAIN_V1").hexdigest()
        check("genesis hash 是确定性种子", SUMMARY_CHAIN_GENESIS_SHA256 == expected_genesis)


# ══════════════════════════════════════════════════════
# B. 锚点签名伪造
# ══════════════════════════════════════════════════════
def test_anchor_forgery() -> None:
    print("\n═══ B. 锚点签名伪造 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        chain_dir = str(Path(tmp) / "chain")
        anchor_dir = str(Path(tmp) / "anchor")
        key_path = str(Path(tmp) / "key")
        Path(key_path).write_text("real-key", encoding="utf-8")
        os.chmod(key_path, 0o600)

        r = _make_record(rid="r-anchor")
        c = append_summary_chain(chain_dir, r, room_id="room-a", source_mode="test")
        export_anchor_bundle(anchor_dir, key_path, c, policy="async")

        # 伪造: 用不同 key 重新签名
        bundle_path = os.path.join(anchor_dir, "room-a", f"{c['turn_summary_sha256']}.json")
        bundle = read_json_file(bundle_path)
        body = {k: v for k, v in bundle.items() if k != "signature"}
        fake_sig = hmac.new(b"fake-key", json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        bundle["signature"] = fake_sig
        atomic_write_json(bundle_path, bundle)

        result = verify_summary_chain(
            os.path.join(chain_dir, "room-a.jsonl"),
            anchor_dir=anchor_dir,
            anchor_key_path=key_path,
        )
        check("伪造签名 → 验证失败", result["ok"] is False and "signature" in result.get("reason", ""))

        # 缺失 key → 跳过签名验证
        result_no_key = verify_summary_chain(
            os.path.join(chain_dir, "room-a.jsonl"),
            anchor_dir=anchor_dir,
            anchor_key_path="",
        )
        check("无 key 仍验证链完整性", result_no_key["ok"] is True)

        # 缺失 key file → 跳过签名
        result_bad_key = verify_summary_chain(
            os.path.join(chain_dir, "room-a.jsonl"),
            anchor_dir=anchor_dir,
            anchor_key_path="/nonexistent/key",
        )
        check("key 文件不存在 → 跳过签名但链通过", result_bad_key["ok"] is True)

        # anchor disabled policy
        disabled = export_anchor_bundle(anchor_dir, key_path, c, policy="disabled")
        check("disabled policy → 不导出", disabled["status"] == "disabled")

        # missing key
        missing_key = export_anchor_bundle(anchor_dir, "/nonexistent/key", c, policy="async")
        check("key 缺失 → 导出失败", missing_key["status"] == "failed")


# ══════════════════════════════════════════════════════
# C. 验证器边界条件
# ══════════════════════════════════════════════════════
def test_verifier_edge_cases() -> None:
    print("\n═══ C. 验证器边界条件 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        # 空文件
        empty_path = os.path.join(tmp, "empty.jsonl")
        Path(empty_path).write_text("", encoding="utf-8")
        result = verify_summary_chain(empty_path)
        check("空链文件 → ok + checked=0", result["ok"] is True and result["checked"] == 0)

        # 不存在的文件
        result2 = verify_summary_chain(os.path.join(tmp, "nonexistent.jsonl"))
        check("不存在文件 → ok=False", result2["ok"] is False)

        # 损坏 JSON
        bad_path = os.path.join(tmp, "bad.jsonl")
        Path(bad_path).write_text("{not valid json\n", encoding="utf-8")
        result3 = verify_summary_chain(bad_path)
        check("损坏 JSON → ok=False", result3["ok"] is False)

        # 删除 anchor bundle 文件
        chain_dir = os.path.join(tmp, "chain")
        anchor_dir = os.path.join(tmp, "anchor")
        key_path = os.path.join(tmp, "key")
        Path(key_path).write_text("key", encoding="utf-8")
        os.chmod(key_path, 0o600)
        r = _make_record()
        c = append_summary_chain(chain_dir, r, room_id="room-v", source_mode="test")
        export_anchor_bundle(anchor_dir, key_path, c, policy="async")
        # 删除 bundle
        bundle_file = os.path.join(anchor_dir, "room-v", f"{c['turn_summary_sha256']}.json")
        os.remove(bundle_file)
        result4 = verify_summary_chain(
            os.path.join(chain_dir, "room-v.jsonl"),
            anchor_dir=anchor_dir,
        )
        check("bundle 文件缺失 → 验证失败", result4["ok"] is False and "missing" in result4.get("reason", ""))


# ══════════════════════════════════════════════════════
# D. atomic_write_json 竞态与边界
# ══════════════════════════════════════════════════════
def test_atomic_write() -> None:
    print("\n═══ D. atomic_write 竞态与边界 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "nested", "deep", "test.json")
        # 自动创建父目录
        atomic_write_json(path, {"key": "value"})
        check("自动创建深层目录", os.path.isfile(path))

        # .tmp 文件不残留
        check(".tmp 文件不残留", not os.path.exists(f"{path}.tmp"))

        # 读回验证
        data = read_json_file(path)
        check("写入数据可回读", data.get("key") == "value")

        # 并发写入同一路径 — 已知限制: atomic_write_json 依赖调用方加锁
        # 生产中所有 call site 都有上层锁保护 (server.lock / PortRegistry._lock / 唯一路径)
        # 此处验证: 每个线程写不同路径时无竞态
        concurrent_errors = []

        def writer(idx: int) -> None:
            try:
                atomic_write_json(os.path.join(tmp, f"concurrent-{idx}.json"), {"writer": idx, "payload": "x" * 1000})
            except Exception as e:
                concurrent_errors.append(str(e))

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        check("50 并发写不同路径无异常", len(concurrent_errors) == 0, str(concurrent_errors[:3]) if concurrent_errors else "")
        sample = read_json_file(os.path.join(tmp, "concurrent-0.json"))
        check("并发写入后文件完整", sample.get("writer") == 0 and sample.get("payload") == "x" * 1000)

        # Unicode 写入
        uni_path = os.path.join(tmp, "unicode.json")
        atomic_write_json(uni_path, {"emoji": "🔥", "中文": "测试"})
        uni_data = read_json_file(uni_path)
        check("Unicode 写入/回读完整", uni_data.get("emoji") == "🔥" and uni_data.get("中文") == "测试")

        # 读取不存在的文件
        check("read_json_file 默认值", read_json_file("/nonexistent/path.json", {"d": 1}) == {"d": 1})


# ══════════════════════════════════════════════════════
# E. append_jsonl 并发完整性
# ══════════════════════════════════════════════════════
def test_append_jsonl_concurrent() -> None:
    print("\n═══ E. append_jsonl 并发完整性 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "concurrent.jsonl")
        errors = []
        N = 200

        def appender(idx: int) -> None:
            try:
                append_jsonl(path, {"idx": idx, "data": f"payload-{idx}"})
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=appender, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        check("200 并发 append 无异常", len(errors) == 0)
        lines = Path(path).read_text(encoding="utf-8").strip().split("\n")
        check(f"行数 = {N}", len(lines) == N, f"实际 {len(lines)}")
        bad = 0
        for line in lines:
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad += 1
        check("所有行合法 JSON", bad == 0, f"bad={bad}")


# ══════════════════════════════════════════════════════
# F. 摘要链并发 + 链完整性
# ══════════════════════════════════════════════════════
def test_summary_chain_concurrent_integrity() -> None:
    print("\n═══ F. 摘要链并发 + 链完整性 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        chain_dir = os.path.join(tmp, "chain")
        anchor_dir = os.path.join(tmp, "anchor")
        key_path = os.path.join(tmp, "key")
        Path(key_path).write_text("concurrent-key", encoding="utf-8")
        os.chmod(key_path, 0o600)

        N = 30
        errors = []

        def chain_writer(idx: int) -> None:
            try:
                r = _make_record(rid=f"r-{idx}", message_body=f"msg-{idx}")
                c = append_summary_chain(chain_dir, r, room_id="room-conc", source_mode="test")
                export_anchor_bundle(anchor_dir, key_path, c, policy="async")
            except Exception as e:
                errors.append(f"writer-{idx}: {e}")

        threads = [threading.Thread(target=chain_writer, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        check(f"{N} 并发链写入无异常", len(errors) == 0, str(errors[:3]) if errors else "")

        chain_path = os.path.join(chain_dir, "room-conc.jsonl")
        lines = Path(chain_path).read_text(encoding="utf-8").strip().split("\n")
        check(f"链条目数 = {N}", len(lines) == N, f"实际 {len(lines)}")

        result = verify_summary_chain(chain_path, anchor_dir=anchor_dir, anchor_key_path=key_path)
        check("并发写入后链验证通过", result["ok"] is True, result.get("reason", ""))
        check(f"验证条目数 = {N}", result["checked"] == N, f"实际 {result['checked']}")


# ══════════════════════════════════════════════════════
# G. PortReservationRegistry 深层对抗
# ══════════════════════════════════════════════════════
def test_port_registry_adversarial() -> None:
    print("\n═══ G. 端口注册表深层对抗 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        reg_path = os.path.join(tmp, "ports.json")

        # 同端口双 owner 冲突
        reg = PortReservationRegistry(reg_path)
        r1 = reg.reserve(12345, "owner-A", {"room": "a"})
        r2 = reg.reserve(12345, "owner-B", {"room": "b"})
        check("同端口不同 owner → 拒绝", r1["granted"] is True and r2["granted"] is False)

        # 同端口同 owner → 幂等
        r3 = reg.reserve(12345, "owner-A", {"room": "a2"})
        check("同端口同 owner → 幂等放行", r3["granted"] is True)

        # release → 再注册
        released = reg.release_owner("owner-A")
        check("release 返回释放的端口", "12345" in released)
        r4 = reg.reserve(12345, "owner-B", {"room": "b"})
        check("release 后他人可注册", r4["granted"] is True)

        # 并发 reserve 同一端口
        reg2 = PortReservationRegistry(os.path.join(tmp, "ports2.json"))
        winners = []
        lock = threading.Lock()

        def race_reserve(idx: int) -> None:
            result = reg2.reserve(9999, f"racer-{idx}")
            if result["granted"]:
                with lock:
                    winners.append(idx)

        threads = [threading.Thread(target=race_reserve, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        check("并发 reserve 同端口只 1 个 winner", len(winners) == 1, f"winners={len(winners)}")

        # reconcile: 不可绑定的端口保留，可绑定的清除
        reg3_path = os.path.join(tmp, "ports3.json")
        free_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        free_sock.bind(("127.0.0.1", 0))
        free_port = int(free_sock.getsockname()[1])
        free_sock.close()  # 释放端口 → reconcile 应清除

        busy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        busy_sock.bind(("127.0.0.1", 0))
        busy_sock.listen(1)
        busy_port = int(busy_sock.getsockname()[1])

        reg3 = PortReservationRegistry(reg3_path)
        reg3.reserve(free_port, "dead-owner")
        reg3.reserve(busy_port, "alive-owner")

        # 重新加载模拟重启
        reg3_reload = PortReservationRegistry(reg3_path)
        events = reg3_reload.reconcile_after_restart()
        kinds = {e["kind"]: e["port"] for e in events}
        check("空闲端口被清除", kinds.get("port_registry_orphan_cleaned") == free_port)
        check("占用端口被保留", kinds.get("port_registry_occupied") == busy_port)

        snap = reg3_reload.snapshot()["reservations"]
        check("reconcile 后快照一致", str(free_port) not in snap and str(busy_port) in snap)

        busy_sock.close()

        # 非法端口 key（非数字）
        reg4_path = os.path.join(tmp, "ports4.json")
        atomic_write_json(reg4_path, {"reservations": {"not-a-port": {"owner": "x"}}})
        reg4 = PortReservationRegistry(reg4_path)
        events4 = reg4.reconcile_after_restart()
        check("非数字 key → port_registry_invalid", any(e["kind"] == "port_registry_invalid" for e in events4))

        # 持久化验证: reserve → 新实例加载
        reg5_path = os.path.join(tmp, "ports5.json")
        reg5 = PortReservationRegistry(reg5_path)
        reg5.reserve(54321, "persist-test")
        reg5_reload = PortReservationRegistry(reg5_path)
        check("持久化后新实例可见", str(54321) in reg5_reload.snapshot()["reservations"])


# ══════════════════════════════════════════════════════
# H. build_turn_summary 边界
# ══════════════════════════════════════════════════════
def test_turn_summary_edge() -> None:
    print("\n═══ H. build_turn_summary 边界 ═══")
    # 空记录
    summary = build_turn_summary({}, room_id="room-e", source_mode="test")
    check("空记录不崩溃", "turn_summary_sha256" in summary)
    check("空记录 schema 正确", summary["schema"] == "trialogue_turn_summary_v1")

    # message body SHA256 正确
    r = _make_record(message_body="test-body")
    s = build_turn_summary(r, room_id="room-e", source_mode="test")
    expected_sha = hashlib.sha256(b"test-body").hexdigest()
    check("message_body_sha256 正确", s["message_body_sha256"] == expected_sha)

    # turn_summary_sha256 排除自身
    body_without_sha = {k: v for k, v in s.items() if k != "turn_summary_sha256"}
    canonical = json.dumps(body_without_sha, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    expected_turn_sha = hashlib.sha256(canonical).hexdigest()
    check("turn_summary_sha256 排除自身后计算", s["turn_summary_sha256"] == expected_turn_sha)

    # 不同 message → 不同 hash
    s2 = build_turn_summary(_make_record(message_body="different"), room_id="room-e", source_mode="test")
    check("不同消息 → 不同 summary hash", s["turn_summary_sha256"] != s2["turn_summary_sha256"])


# ══════════════════════════════════════════════════════
# I. 链 genesis 验证
# ══════════════════════════════════════════════════════
def test_chain_genesis() -> None:
    print("\n═══ I. 链 genesis 验证 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        chain_dir = os.path.join(tmp, "chain")
        r = _make_record()
        c = append_summary_chain(chain_dir, r, room_id="room-g", source_mode="test")

        # 首条 prev 必须是 genesis
        check("首条 prev = genesis", c["prev_summary_sha256"] == SUMMARY_CHAIN_GENESIS_SHA256)
        check("genesis hash 返回", c["genesis_summary_sha256"] == SUMMARY_CHAIN_GENESIS_SHA256)

        # 第二条 prev = 第一条 turn_sha
        r2 = _make_record(rid="r2")
        c2 = append_summary_chain(chain_dir, r2, room_id="room-g", source_mode="test")
        check("第二条 prev = 第一条 turn_sha", c2["prev_summary_sha256"] == c["turn_summary_sha256"])


# ══════════════════════════════════════════════════════
# J. TMPDIR 隔离验证
# ══════════════════════════════════════════════════════
def test_tmpdir_isolation() -> None:
    print("\n═══ J. TMPDIR 隔离验证 ═══")
    # start.sh 和 start-web.sh 都设置 TMPDIR=$PRIVATE_TMP_DIR
    for script in ("start.sh", "start-web.sh"):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(script_dir, script)
        if os.path.isfile(script_path):
            content = Path(script_path).read_text(encoding="utf-8")
            has_tmpdir = "export TMPDIR=${PRIVATE_TMP_DIR}" in content or "export TMPDIR=" in content
            check(f"{script} 设置 TMPDIR", has_tmpdir)
            has_chmod = "chmod 600" in content
            check(f"{script} env 文件权限 600", has_chmod)
        else:
            check(f"{script} 存在", False, "file not found")


def main() -> int:
    test_summary_chain_tampering()
    test_anchor_forgery()
    test_verifier_edge_cases()
    test_atomic_write()
    test_append_jsonl_concurrent()
    test_summary_chain_concurrent_integrity()
    test_port_registry_adversarial()
    test_turn_summary_edge()
    test_chain_genesis()
    test_tmpdir_isolation()

    print(f"\n{'═' * 50}")
    print(f"通过: {PASSED}  失败: {FAILED}")
    if FAILED == 0:
        print("P1-2/3/4 敌对审查全部通过")
    else:
        print("存在失败项")
    print(f"{'═' * 50}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
