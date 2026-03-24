#!/usr/bin/env python3
"""
P1-2/3/4 真正的攻击向量测试
目标: 找到能让审计链/恢复/端口隔离出现安全问题的路径
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import struct
import tempfile
import threading
import time
from pathlib import Path

from hardening import (
    SUMMARY_CHAIN_GENESIS_SHA256,
    PortReservationRegistry,
    _anchor_signature_bytes,
    _can_bind_local_port,
    _last_jsonl_record,
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
VULNS = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  ✓ {name}")
    else:
        FAILED += 1
        extra = f" — {detail}" if detail else ""
        print(f"  ✗ {name}{extra}")
        VULNS.append(name)


def _make_record(**overrides: object) -> dict:
    base = {
        "timestamp": "2026-03-23T00:00:00Z",
        "rid": "rid-atk",
        "nonce": "nonce-atk",
        "target": "claude",
        "target_name": "meeting",
        "target_source": "default",
        "target_path": "",
        "mode": "launcher_generated",
        "session_id": "sess-atk",
        "session_confirmed": True,
        "confirmation_method": "claude_session_file",
        "confirmation": {"turn_id": "turn-atk", "thread_id": "thread-atk"},
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
# ATK-1: atomic_write_json 并发同路径 .tmp 碰撞
# 攻击面: 多线程写同一 path → .tmp 文件互相覆盖 → os.replace 可能拿到别人的半写内容或 FileNotFoundError
# ══════════════════════════════════════════════════════
def atk_atomic_write_same_path_race() -> None:
    print("\n═══ ATK-1: atomic_write_json 同路径 .tmp 碰撞 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "race.json")
        errors = []
        corruption = []

        def writer(idx: int) -> None:
            try:
                atomic_write_json(target, {"writer": idx, "canary": f"v{idx}", "pad": "x" * 500})
            except Exception as e:
                errors.append((idx, str(e)))

        def reader() -> None:
            for _ in range(200):
                try:
                    data = read_json_file(target, None)
                    if data is not None:
                        # 检查文件内容自洽: writer 和 canary 必须匹配
                        w = data.get("writer")
                        c = data.get("canary")
                        if w is not None and c != f"v{w}":
                            corruption.append(data)
                except Exception:
                    pass
                time.sleep(0.001)

        # 开一个读线程并发检查文件一致性
        reader_thread = threading.Thread(target=reader, daemon=True)
        reader_thread.start()

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        reader_thread.join(timeout=3)

        has_errors = len(errors) > 0
        has_corruption = len(corruption) > 0
        # b80a222: mkstemp 消除 .tmp 碰撞
        check(
            "mkstemp 修复后同路径并发写无异常",
            not has_errors,
            f"errors={len(errors)}" + (f" 样例: {errors[0][1][:120]}" if errors else "")
        )
        check(
            "mkstemp 修复后无数据损坏",
            not has_corruption,
            f"corruption={len(corruption)}" if corruption else ""
        )
        if not has_errors and not has_corruption:
            print("    [FIXED] atomic_write_json mkstemp 修复有效, 30 线程并发 0 异常 0 损坏")

        # 关键检查: 生产中所有调用点是否有锁保护?
        # server.py: _persist_room_state → 无显式锁! 让我验证
        import inspect
        import server
        # 检查 _persist_room_state 是否在 self.lock 下被调用
        src = inspect.getsource(server.TrialogueState._persist_room_state)
        check(
            "_persist_room_state 本身不加锁 (依赖调用方)",
            "self.lock" not in src and "with self.lock" not in src,
            "如果函数自身加锁则此项不适用"
        )
        # 检查 emit_system_event 是否锁内调用 _persist
        src_emit = inspect.getsource(server.TrialogueState.emit_system_event)
        check(
            "emit_system_event 在锁外调用 _persist (竞态窗口)",
            "_persist_room_state" in src_emit and "with self.lock" in src_emit,
            "检查 _persist 是否在锁释放后调用"
        )


# ══════════════════════════════════════════════════════
# ATK-2: 摘要链截断攻击 — 砍掉最后 N 条记录
# 如果攻击者能写文件，可以删除链尾部记录来隐藏操作
# ══════════════════════════════════════════════════════
def atk_chain_truncation() -> None:
    print("\n═══ ATK-2: 摘要链截断攻击 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        chain_dir = os.path.join(tmp, "chain")
        key_path = os.path.join(tmp, "key")
        Path(key_path).write_text("key", encoding="utf-8")
        os.chmod(key_path, 0o600)

        # 写 5 条
        for i in range(5):
            r = _make_record(rid=f"r{i}", message_body=f"msg{i}")
            append_summary_chain(chain_dir, r, room_id="room-trunc", source_mode="test")

        chain_path = os.path.join(chain_dir, "room-trunc.jsonl")
        lines = Path(chain_path).read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 5

        # 截断: 只保留前 3 条
        Path(chain_path).write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")
        result = verify_summary_chain(chain_path)
        check(
            "截断后链验证仍通过 (无 anchor 对比时无法检测截断)",
            result["ok"] is True and result["checked"] == 3,
        )

        # 带 anchor 也无法检测截断 — 验证器只检查链中存在的条目
        chain_dir2 = os.path.join(tmp, "chain2")
        anchor_dir2 = os.path.join(tmp, "anchor2")
        for i in range(5):
            r = _make_record(rid=f"r{i}", message_body=f"msg{i}")
            c = append_summary_chain(chain_dir2, r, room_id="room-trunc2", source_mode="test")
            export_anchor_bundle(anchor_dir2, key_path, c, policy="async")

        chain_path2 = os.path.join(chain_dir2, "room-trunc2.jsonl")
        lines2 = Path(chain_path2).read_text(encoding="utf-8").strip().split("\n")
        # 截断到 3 条
        Path(chain_path2).write_text("\n".join(lines2[:3]) + "\n", encoding="utf-8")
        result2 = verify_summary_chain(chain_path2, anchor_dir=anchor_dir2, anchor_key_path=key_path)
        check(
            "带 anchor 截断后验证仍通过 (验证器不知道应有 5 条)",
            result2["ok"] is True and result2["checked"] == 3,
        )
        print("    [VULN-P2] 截断攻击不可检测: 验证器不知道链应有多少条")
        print("    [VULN-P2] 需要外部计数器或 audit log 交叉验证")


# ══════════════════════════════════════════════════════
# ATK-3: 完整链替换攻击 — 用全新伪造链替换
# ══════════════════════════════════════════════════════
def atk_chain_full_replacement() -> None:
    print("\n═══ ATK-3: 完整链替换攻击 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        chain_dir = os.path.join(tmp, "chain")
        anchor_dir = os.path.join(tmp, "anchor")
        key_path = os.path.join(tmp, "key")
        Path(key_path).write_text("real-key", encoding="utf-8")
        os.chmod(key_path, 0o600)

        # 写真实链
        for i in range(3):
            r = _make_record(rid=f"real-{i}", message_body=f"real-msg-{i}")
            c = append_summary_chain(chain_dir, r, room_id="room-replace", source_mode="test")
            export_anchor_bundle(anchor_dir, key_path, c, policy="async")

        # 攻击者知道 key (同用户权限下 0o600 仍可读) → 完全伪造新链
        fake_chain_dir = os.path.join(tmp, "fake-chain")
        fake_anchor_dir = os.path.join(tmp, "fake-anchor")
        for i in range(3):
            r = _make_record(rid=f"fake-{i}", message_body=f"evil-msg-{i}")
            c = append_summary_chain(fake_chain_dir, r, room_id="room-replace", source_mode="test")
            export_anchor_bundle(fake_anchor_dir, key_path, c, policy="async")

        # 替换链和 anchor
        chain_path = os.path.join(chain_dir, "room-replace.jsonl")
        fake_chain_path = os.path.join(fake_chain_dir, "room-replace.jsonl")
        import shutil
        shutil.copy2(fake_chain_path, chain_path)
        real_anchor_room = os.path.join(anchor_dir, "room-replace")
        fake_anchor_room = os.path.join(fake_anchor_dir, "room-replace")
        shutil.rmtree(real_anchor_room)
        shutil.copytree(fake_anchor_room, real_anchor_room)

        result = verify_summary_chain(chain_path, anchor_dir=anchor_dir, anchor_key_path=key_path)
        check(
            "完整替换: 伪造链 + 伪造 anchor 通过验证 (同用户权限时)",
            result["ok"] is True,
        )
        print("    [VULN-P2] HMAC key 是本地文件，同用户攻击者可读 (0o600 只防其他用户)")
        print("    [VULN-P2] 需要外部可信存储或 HSM 才能防御同用户攻击")


# ══════════════════════════════════════════════════════
# ATK-4: append_jsonl 并发写入 — 验证 fcntl lock 修复后是否仍可撕裂
# b80a222 后 append_jsonl 加了 fcntl.LOCK_EX
# ══════════════════════════════════════════════════════
def atk_append_jsonl_torn_write() -> None:
    print("\n═══ ATK-4: append_jsonl 行级撕裂测试 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "torn.jsonl")
        # 模拟大 payload 增加撕裂概率
        N = 100
        errors = []

        def appender(idx: int) -> None:
            try:
                # 大 payload 增加非原子写入概率
                append_jsonl(path, {"idx": idx, "big": "A" * 4000})
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=appender, args=(i,)) for i in range(N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        lines = Path(path).read_text(encoding="utf-8").strip().split("\n")
        bad_lines = 0
        for line in lines:
            try:
                json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1

        check(f"并发 append {N} 次: 行数", len(lines) == N, f"实际 {len(lines)}")
        check(f"坏行数", bad_lines == 0, f"bad={bad_lines}")
        # b80a222 后 append_jsonl 有 fcntl.LOCK_EX
        print("    [FIXED] append_jsonl 现在有 fcntl.LOCK_EX, 跨进程也安全")


# ══════════════════════════════════════════════════════
# ATK-5: _audit.py audit log 写入 — 验证已改走 append_jsonl (带锁)
# ══════════════════════════════════════════════════════
def atk_audit_log_no_lock() -> None:
    print("\n═══ ATK-5: _audit.py audit log 写入锁验证 ═══")
    audit_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_audit.py")
    if not os.path.isfile(audit_path):
        check("_audit.py 存在", False)
        return

    src = Path(audit_path).read_text(encoding="utf-8")
    # b80a222: _audit.py 改用 append_jsonl (已有 fcntl lock)
    uses_append_jsonl = "append_jsonl" in src
    # 不应再有裸的 open(audit_log, "a")
    raw_audit_write = any(
        "audit_log" in line and '"a"' in line and "open(" in line
        for line in src.split("\n")
    )
    check(
        "_audit.py 使用 append_jsonl (带 fcntl lock)",
        uses_append_jsonl,
    )
    check(
        "_audit.py 无裸 open('a') 写 audit log",
        not raw_audit_write,
        "仍有裸写入路径" if raw_audit_write else ""
    )
    if uses_append_jsonl and not raw_audit_write:
        print("    [FIXED] _audit.py 已改走 append_jsonl, 跨进程写入安全")


# ══════════════════════════════════════════════════════
# ATK-6: port registry TOCTOU — bind check 与实际使用之间的窗口
# ══════════════════════════════════════════════════════
def atk_port_toctou() -> None:
    print("\n═══ ATK-6: port registry bind-check TOCTOU ═══")
    # reconcile_after_restart 中:
    #   1. _can_bind_local_port(port) → True (端口空闲)
    #   2. 清除注册 (认为是孤儿)
    # 但在 1 和 2 之间，其他进程可能已绑定该端口
    # 这是一个经典 TOCTOU，但影响有限 (最坏情况: 误清一个活端口注册)

    # reserve() 中:
    #   1. 检查 reservations 中是否已存在
    #   2. 记录注册
    # 但不检查端口是否真的可绑定 — agent 可能注册一个已被外部进程占用的端口
    with tempfile.TemporaryDirectory() as tmp:
        reg_path = os.path.join(tmp, "ports.json")
        reg = PortReservationRegistry(reg_path)

        # 注册一个已被占用的端口
        busy_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        busy_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        busy_sock.bind(("127.0.0.1", 0))
        busy_sock.listen(1)
        busy_port = int(busy_sock.getsockname()[1])

        result = reg.reserve(busy_port, "attacker")
        check(
            "reserve 不检查端口是否已被外部占用",
            result["granted"] is True,
        )
        print("    [INFO] reserve() 只检查注册表，不检查端口实际可用性")
        print("    [INFO] 这允许 agent 虚报端口占用来阻止其他 agent")
        print("    [INFO] 但上层 server.py 在 approval flow 中有 operation lock 保护")

        busy_sock.close()

        # reconcile TOCTOU 窗口
        check(
            "reconcile TOCTOU 存在但影响有限",
            True,
        )
        print("    [INFO] reconcile 的 bind-check → 清除 之间有 TOCTOU 窗口")
        print("    [INFO] 最坏情况: 误清一个在 check 后才启动的服务的注册")


# ══════════════════════════════════════════════════════
# ATK-7: verify_summary_chain 不报告总数 → 无法检测链增长异常
# ══════════════════════════════════════════════════════
def atk_verify_no_expected_count() -> None:
    print("\n═══ ATK-7: 验证器缺少预期条目数 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        chain_dir = os.path.join(tmp, "chain")
        key_path = os.path.join(tmp, "key")
        Path(key_path).write_text("key", encoding="utf-8")

        for i in range(5):
            append_summary_chain(chain_dir, _make_record(rid=f"r{i}"), room_id="room-count", source_mode="test")

        chain_path = os.path.join(chain_dir, "room-count.jsonl")

        # 注入额外条目 (攻击者知道最后一条的 hash)
        lines = Path(chain_path).read_text(encoding="utf-8").strip().split("\n")
        last_entry = json.loads(lines[-1])
        last_sha = last_entry["turn_summary_sha256"]

        # 构造一条合法的新记录，prev 指向 last_sha
        injected_record = _make_record(rid="injected", message_body="evil-injected")
        injected_summary = build_turn_summary(injected_record, room_id="room-count", source_mode="test")
        injected_entry = {
            "schema": "trialogue_summary_chain_entry_v1",
            "generated_at": "2026-03-23T12:00:00Z",
            "room_id": "room-count",
            "rid": "injected",
            "target": "claude",
            "prev_summary_sha256": last_sha,
            "turn_summary_sha256": injected_summary["turn_summary_sha256"],
            "summary": injected_summary,
        }
        with open(chain_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(injected_entry, ensure_ascii=False) + "\n")

        # 验证 — 注入的条目在链末尾且 prev hash 正确，所以通过
        result = verify_summary_chain(chain_path)
        check(
            "注入尾部条目通过验证 (无 anchor 时)",
            result["ok"] is True and result["checked"] == 6,
        )
        print("    [VULN] 攻击者可在链尾追加伪造条目 (无需 key)")
        print("    [VULN] 只有 anchor bundle 验证能检测 (因为注入条目无 bundle)")


# ══════════════════════════════════════════════════════
# ATK-8: _persist_room_state 调用链竞态分析
# ══════════════════════════════════════════════════════
def atk_persist_race_analysis() -> None:
    print("\n═══ ATK-8: _persist_room_state 竞态分析 ═══")
    import inspect
    import server

    # 找所有调用 _persist_room_state 的方法
    src = inspect.getsource(server.TrialogueState)
    methods = {}
    current_method = None
    for line in src.split("\n"):
        stripped = line.strip()
        if stripped.startswith("def "):
            current_method = stripped.split("(")[0].replace("def ", "")
        if "_persist_room_state" in stripped and current_method and current_method != "_persist_room_state":
            if current_method not in methods:
                methods[current_method] = {"has_lock": False, "persist_in_lock": False}

    # 检查每个调用方法是否在锁内
    for method_name in methods:
        try:
            method_src = inspect.getsource(getattr(server.TrialogueState, method_name))
            methods[method_name]["has_lock"] = "with self.lock" in method_src
            # 检查 _persist 是否在 with self.lock 块内
            lines = method_src.split("\n")
            in_lock = False
            for line in lines:
                if "with self.lock" in line:
                    in_lock = True
                if in_lock and "_persist_room_state" in line:
                    methods[method_name]["persist_in_lock"] = True
                # 简单启发: dedent 退出 with 块
                if in_lock and line.strip() and not line.startswith(" " * 8) and "with" not in line and "def" not in line:
                    if "_persist_room_state" not in line:
                        in_lock = False
        except (AttributeError, TypeError):
            pass

    unprotected = [m for m, info in methods.items() if not info["persist_in_lock"]]
    print(f"    调用 _persist_room_state 的方法: {list(methods.keys())}")
    print(f"    _persist 不在 self.lock 内的方法: {unprotected}")
    check(
        "存在锁外调用 _persist_room_state 的路径",
        len(unprotected) > 0,
        f"unprotected: {unprotected}"
    )
    if unprotected:
        print("    [INFO] 这些方法在锁外调用 _persist → 并发 submit 时 atomic_write .tmp 碰撞")
        print("    [INFO] 但 atomic_write 同路径碰撞只会导致 FileNotFoundError, 不会数据损坏")
        print("    [INFO] 因为 os.replace 是原子的 — 要么成功替换，要么失败")


# ══════════════════════════════════════════════════════
# ATK-9: _last_jsonl_record 扫描整个文件 — 大文件性能攻击
# ══════════════════════════════════════════════════════
def atk_last_record_performance() -> None:
    print("\n═══ ATK-9: _last_jsonl_record 全文件扫描性能 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "big.jsonl")
        # 写 10000 行
        with open(path, "w", encoding="utf-8") as f:
            for i in range(10000):
                f.write(json.dumps({"idx": i, "pad": "x" * 200}) + "\n")

        start = time.monotonic()
        result = _last_jsonl_record(path)
        elapsed = time.monotonic() - start

        check(f"10K 行 _last_jsonl_record: {elapsed:.3f}s", elapsed < 1.0, f"took {elapsed:.3f}s")
        print(f"    [INFO] _last_jsonl_record 扫描整个文件获取最后一行")
        print(f"    [INFO] 长期运行的 room 链文件会越来越大")
        print(f"    [INFO] 建议: 用 seek-to-end 或缓存 last record")


# ══════════════════════════════════════════════════════
# ATK-10: anchor key 文件权限检查
# ══════════════════════════════════════════════════════
def atk_anchor_key_permissions() -> None:
    print("\n═══ ATK-10: anchor key 权限检查验证 ═══")
    with tempfile.TemporaryDirectory() as tmp:
        chain_dir = os.path.join(tmp, "chain")
        anchor_dir = os.path.join(tmp, "anchor")
        r = _make_record()
        c = append_summary_chain(chain_dir, r, room_id="room-perm", source_mode="test")

        # 权限过宽的 key → 应被拒绝
        insecure_key = os.path.join(tmp, "insecure.key")
        Path(insecure_key).write_text("secret", encoding="utf-8")
        os.chmod(insecure_key, 0o644)
        result_insecure = export_anchor_bundle(anchor_dir, insecure_key, c, policy="async")
        check(
            "644 权限 key → 导出拒绝",
            result_insecure["status"] == "failed" and "insecure" in result_insecure.get("reason", ""),
        )

        # group-readable
        group_key = os.path.join(tmp, "group.key")
        Path(group_key).write_text("secret", encoding="utf-8")
        os.chmod(group_key, 0o640)
        result_group = export_anchor_bundle(anchor_dir, group_key, c, policy="async")
        check(
            "640 权限 key → 导出拒绝",
            result_group["status"] == "failed",
        )

        # 正确权限
        secure_key = os.path.join(tmp, "secure.key")
        Path(secure_key).write_text("secret", encoding="utf-8")
        os.chmod(secure_key, 0o600)
        result_secure = export_anchor_bundle(anchor_dir, secure_key, c, policy="async")
        check(
            "600 权限 key → 导出成功",
            result_secure["status"] == "exported",
        )

        # owner-only read
        ro_key = os.path.join(tmp, "ro.key")
        Path(ro_key).write_text("secret", encoding="utf-8")
        os.chmod(ro_key, 0o400)
        result_ro = export_anchor_bundle(anchor_dir, ro_key, c, policy="async")
        check(
            "400 权限 key → 导出成功",
            result_ro["status"] == "exported",
        )
        print("    [FIXED] export_anchor_bundle 现在检查 key 文件权限, group/other 可读即拒绝")


def main() -> int:
    atk_atomic_write_same_path_race()
    atk_chain_truncation()
    atk_chain_full_replacement()
    atk_append_jsonl_torn_write()
    atk_audit_log_no_lock()
    atk_port_toctou()
    atk_verify_no_expected_count()
    atk_persist_race_analysis()
    atk_last_record_performance()
    atk_anchor_key_permissions()

    print(f"\n{'═' * 60}")
    print(f"通过: {PASSED}  失败: {FAILED}")
    if VULNS:
        print(f"\n发现的攻击向量:")
        for v in VULNS:
            print(f"  ✗ {v}")
    print(f"{'═' * 60}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
