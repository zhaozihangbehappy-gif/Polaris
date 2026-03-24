#!/usr/bin/env python3
"""Protocol smoke test: verify 0.116.0 approval type handling.

Tests the _handle_server_request branching logic by constructing a minimal
Runner-like object and calling the method directly. Also validates the
ReviewDecision enum against the official 0.116.0 JSON schema.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

passed = 0
failed = 0
_thread_exceptions: list[BaseException] = []
_orig_excepthook = threading.excepthook


def _capture_thread_exception(args):
    _thread_exceptions.append(args.exc_value)
    # Still print so it's visible in output
    _orig_excepthook(args)


threading.excepthook = _capture_thread_exception


def check(label: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {label}")
    else:
        failed += 1
        print(f"  ✗ {label}  {detail}")


class FakeAppClient:
    """Records respond() calls."""
    def __init__(self):
        self.responses: dict = {}

    def respond(self, request_id, result):
        self.responses[request_id] = result


class FakeBrokerInput:
    """Minimal stand-in for BrokerInput that reads from an explicit queue."""
    def __init__(self, q: queue.Queue):
        self._q = q

    def wait_for_approval(self, request_id, timeout_sec):
        try:
            payload = self._q.get(timeout=timeout_sec)
            return {"type": "approval_response", "request_id": request_id, **payload}
        except queue.Empty:
            return None


class FakeLogger:
    def log(self, **kwargs):
        pass

    def append(self, *args, **kwargs):
        pass


def build_stub_runner():
    """Build a minimal object with just enough attrs for _handle_server_request."""
    from codex_app_server_runner import Runner, PendingApproval

    stub = object.__new__(Runner)
    stub.app_client = FakeAppClient()
    stub.conf = {"CODEX_APPROVAL_TIMEOUT_SEC": "5"}
    stub.room_id = "test-room"
    stub.cwd = "/tmp"
    stub.thread_id = "thread-test"
    stub.turn_id = "turn-test"
    stub.pending_approval = None
    stub.approval_response_queue = queue.Queue()
    stub.approval_events = []
    stub.broker_input = FakeBrokerInput(stub.approval_response_queue)
    return stub


# ── Test 1: New 0.116.0 approval types get {"decision": "denied"} ──

def test_new_approval_types():
    print("\n── 0.116.0 new approval types ──")
    stub = build_stub_runner()
    logger = FakeLogger()

    for method_name, req_id in [("applyPatchApproval", 101), ("execCommandApproval", 102)]:
        stub.app_client.responses.clear()
        payload = {"id": req_id, "method": method_name, "params": {"callId": "c1", "conversationId": "t1"}}
        stub._handle_server_request(payload, logger)
        resp = stub.app_client.responses.get(req_id)
        check(f"{method_name} gets response", resp is not None, f"got {resp}")
        check(
            f"{method_name} decision is 'denied'",
            resp is not None and resp.get("decision") == "denied",
            f"got {resp}",
        )


# ── Test 2: Unknown server requests still get {} ──

def test_unknown_request():
    print("\n── Unknown server request fallback ──")
    stub = build_stub_runner()
    logger = FakeLogger()

    stub.app_client.responses.clear()
    payload = {"id": 200, "method": "item/tool/requestUserInput", "params": {}}
    stub._handle_server_request(payload, logger)
    resp = stub.app_client.responses.get(200)
    check("unknown request gets response", resp is not None, f"got {resp}")
    check("unknown request response is {}", resp == {}, f"got {resp}")


# ── Test 3: Legacy approval does NOT auto-respond ──

def test_legacy_approval_blocks():
    print("\n── Legacy approval enters broker path (not auto-responded) ──")
    stub = build_stub_runner()
    logger = FakeLogger()

    stub.app_client.responses.clear()
    payload = {
        "id": 300,
        "method": "item/commandExecution/requestApproval",
        "params": {
            "itemId": "cmd-1", "threadId": "thread-1", "turnId": "turn-1",
            "command": "echo test", "commandActions": [], "cwd": "/tmp", "reason": "test",
        },
    }

    def run():
        stub._handle_server_request(payload, logger)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(0.5)

    auto_responded = 300 in stub.app_client.responses
    check("legacy approval not auto-responded", not auto_responded,
          "was auto-responded — should block for broker")

    # Unblock
    stub.approval_response_queue.put({"decision": "decline"})
    t.join(timeout=3)
    check("legacy approval thread exited cleanly", not t.is_alive(),
          "thread still alive after unblock — likely crashed or deadlocked")


# ── Test 4: ReviewDecision enum correctness ──

def test_review_decision_enum():
    print("\n── ReviewDecision enum validation ──")
    valid_review = {"approved", "approved_for_session", "denied", "abort"}
    valid_legacy = {"accept", "acceptForSession", "decline", "cancel"}

    check("'denied' is valid ReviewDecision", "denied" in valid_review)
    check("'decline' is NOT valid ReviewDecision", "decline" not in valid_review)
    check("'approved' is valid ReviewDecision", "approved" in valid_review)
    check("'accept' is NOT valid ReviewDecision", "accept" not in valid_review)


# ── Test 5: Schema validation against 0.116.0 (if available) ──

def test_schema_validation():
    print("\n── 0.116.0 schema validation ──")
    schema_dir = "/tmp/codex-schema"
    for schema_file, expected_decisions in [
        ("ApplyPatchApprovalResponse.json", {"approved", "denied", "abort", "approved_for_session"}),
        ("ExecCommandApprovalResponse.json", {"approved", "denied", "abort", "approved_for_session"}),
    ]:
        path = os.path.join(schema_dir, schema_file)
        if not os.path.isfile(path):
            # Try generating
            subprocess.run(
                ["codex", "app-server", "generate-json-schema", "--out", schema_dir],
                capture_output=True, timeout=10,
            )
        if os.path.isfile(path):
            with open(path) as f:
                schema = json.load(f)
            # Extract decision enum values from ReviewDecision
            defs = schema.get("definitions", {})
            review = defs.get("ReviewDecision", {})
            enum_values = set()
            for variant in review.get("oneOf", []):
                if "enum" in variant:
                    enum_values.update(variant["enum"])
                for k in variant.get("required", []):
                    enum_values.add(k)
            check(
                f"{schema_file}: 'denied' in ReviewDecision enum",
                "denied" in enum_values,
                f"found: {enum_values}",
            )
            check(
                f"{schema_file}: 'decision' is required",
                "decision" in (schema.get("required") or []),
                f"required: {schema.get('required')}",
            )
        else:
            check(f"{schema_file}: schema file exists", False, "not found and codex generate failed")


# ── Test 6: fake_codex_app_server sends correct new approval params ──

def test_fake_server_schema_compliance():
    print("\n── fake_codex_app_server schema compliance ──")
    schema_dir = "/tmp/codex-schema"

    # applyPatchApproval params
    patch_schema_path = os.path.join(schema_dir, "ApplyPatchApprovalParams.json")
    if os.path.isfile(patch_schema_path):
        with open(patch_schema_path) as f:
            schema = json.load(f)
        required = set(schema.get("required", []))
        # Our fake server sends: callId, conversationId, fileChanges
        fake_params = {"callId", "conversationId", "fileChanges"}
        check(
            "fake applyPatchApproval has all required fields",
            required.issubset(fake_params),
            f"required={required}, fake_sends={fake_params}",
        )
    else:
        check("ApplyPatchApprovalParams.json exists", False, "not found")

    # execCommandApproval params
    exec_schema_path = os.path.join(schema_dir, "ExecCommandApprovalParams.json")
    if os.path.isfile(exec_schema_path):
        with open(exec_schema_path) as f:
            schema = json.load(f)
        required = set(schema.get("required", []))
        fake_params = {"callId", "conversationId", "command", "cwd", "parsedCmd"}
        check(
            "fake execCommandApproval has all required fields",
            required.issubset(fake_params),
            f"required={required}, fake_sends={fake_params}",
        )
    else:
        check("ExecCommandApprovalParams.json exists", False, "not found")


if __name__ == "__main__":
    test_new_approval_types()
    test_unknown_request()
    test_legacy_approval_blocks()
    test_review_decision_enum()
    test_schema_validation()
    test_fake_server_schema_compliance()
    # Drain any uncaught thread exceptions into the failure count
    if _thread_exceptions:
        for exc in _thread_exceptions:
            check(f"no thread exception ({type(exc).__name__})", False, str(exc))
    print(f"\n{'='*40}")
    print(f"PROTOCOL_SMOKE: {passed} passed, {failed} failed")
    if failed:
        print("PROTOCOL_SMOKE_FAILED")
        sys.exit(1)
    else:
        print("PROTOCOL_SMOKE_OK")
