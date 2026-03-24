#!/usr/bin/env python3
"""Minimal fake Codex CLI for local app-server runner tests."""

from __future__ import annotations

import json
import sys


def send(payload):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", **payload}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_version():
    print("fake-codex 0.0.1")


def handle_app_server():
    thread_id = "thread-fake-001"
    thread_path = "/srv/trialogue/codex/home/.codex/sessions/fake-thread-fake-001.jsonl"
    turn_id = "turn-fake-001"
    while True:
        raw = sys.stdin.readline()
        if not raw:
            break
        msg = json.loads(raw)
        method = msg.get("method")
        if method == "initialize":
            send({"id": msg["id"], "result": {"serverInfo": {"name": "fake", "version": "0.0.1"}}})
        elif method == "initialized":
            continue
        elif method == "thread/start":
            send(
                {
                    "id": msg["id"],
                    "result": {
                        "approvalPolicy": "on-request",
                        "cwd": msg["params"].get("cwd", "/srv/trialogue/codex/workspace"),
                        "model": "fake-model",
                        "modelProvider": "fake",
                        "sandbox": {"type": "workspaceWrite", "writableRoots": [], "networkAccess": False},
                        "thread": {
                            "id": thread_id,
                            "path": thread_path,
                            "createdAt": 0,
                            "updatedAt": 0,
                            "cwd": msg["params"].get("cwd", "/srv/trialogue/codex/workspace"),
                            "ephemeral": False,
                            "cliVersion": "fake-codex 0.0.1",
                            "modelProvider": "fake",
                            "preview": "fake preview",
                            "source": "codex app-server",
                            "status": "idle",
                            "turns": [],
                        },
                    },
                }
            )
            send(
                {
                    "method": "thread/started",
                    "params": {
                        "thread": {
                            "id": thread_id,
                            "path": thread_path,
                            "createdAt": 0,
                            "updatedAt": 0,
                            "cwd": msg["params"].get("cwd", "/srv/trialogue/codex/workspace"),
                            "ephemeral": False,
                            "cliVersion": "fake-codex 0.0.1",
                            "modelProvider": "fake",
                            "preview": "fake preview",
                            "source": "codex app-server",
                            "status": "idle",
                            "turns": [],
                        }
                    },
                }
            )
        elif method == "thread/resume":
            send(
                {
                    "id": msg["id"],
                    "result": {
                        "approvalPolicy": "on-request",
                        "cwd": msg["params"].get("cwd", "/srv/trialogue/codex/workspace"),
                        "model": "fake-model",
                        "modelProvider": "fake",
                        "sandbox": {"type": "workspaceWrite", "writableRoots": [], "networkAccess": False},
                        "thread": {
                            "id": msg["params"]["threadId"],
                            "path": thread_path,
                            "createdAt": 0,
                            "updatedAt": 0,
                            "cwd": msg["params"].get("cwd", "/srv/trialogue/codex/workspace"),
                            "ephemeral": False,
                            "cliVersion": "fake-codex 0.0.1",
                            "modelProvider": "fake",
                            "preview": "fake preview",
                            "source": "codex app-server",
                            "status": "idle",
                            "turns": [],
                        },
                    },
                }
            )
        elif method == "turn/start":
            send({"id": msg["id"], "result": {"turn": {"id": turn_id, "status": "inProgress", "items": []}}})
            send({"method": "turn/started", "params": {"threadId": thread_id, "turn": {"id": turn_id, "status": "inProgress", "items": []}}})
            send(
                {
                    "id": 7001,
                    "method": "item/commandExecution/requestApproval",
                    "params": {
                        "itemId": "cmd-1",
                        "threadId": thread_id,
                        "turnId": turn_id,
                        "command": "echo fake-command",
                        "commandActions": [],
                        "cwd": msg["params"].get("cwd", "/srv/trialogue/codex/workspace"),
                        "reason": "fake approval path",
                    },
                }
            )
            approval = json.loads(sys.stdin.readline())
            send({"method": "serverRequest/resolved", "params": {"requestId": 7001, "threadId": thread_id}})
            decision = approval.get("result", {}).get("decision", "decline")
            # Normalize: both legacy (accept/acceptForSession) and
            # 0.116.0+ ReviewDecision (approved/approved_for_session) mean "allow"
            _is_approved = decision in ("accept", "acceptForSession", "approved", "approved_for_session")
            # 0.116.0+ applyPatchApproval (ReviewDecision enum: approved/denied/abort)
            send(
                {
                    "id": 7002,
                    "method": "applyPatchApproval",
                    "params": {
                        "callId": "patch-call-1",
                        "conversationId": thread_id,
                        "fileChanges": {
                            "/tmp/fake-file.txt": {
                                "type": "add",
                                "content": "fake content",
                            }
                        },
                    },
                }
            )
            patch_approval = json.loads(sys.stdin.readline())
            patch_decision = patch_approval.get("result", {}).get("decision", "denied")
            send({"method": "serverRequest/resolved", "params": {"requestId": 7002, "threadId": thread_id}})
            # 0.116.0+ execCommandApproval (ReviewDecision enum: approved/denied/abort)
            send(
                {
                    "id": 7003,
                    "method": "execCommandApproval",
                    "params": {
                        "callId": "exec-call-1",
                        "conversationId": thread_id,
                        "command": ["echo", "fake-exec"],
                        "cwd": msg["params"].get("cwd", "/srv/trialogue/codex/workspace"),
                        "parsedCmd": [{"type": "unknown", "cmd": "echo fake-exec"}],
                    },
                }
            )
            exec_approval = json.loads(sys.stdin.readline())
            exec_decision = exec_approval.get("result", {}).get("decision", "denied")
            send({"method": "serverRequest/resolved", "params": {"requestId": 7003, "threadId": thread_id}})
            send(
                {
                    "method": "item/completed",
                    "params": {
                        "threadId": thread_id,
                        "turnId": turn_id,
                        "item": {
                            "id": "cmd-1",
                            "type": "commandExecution",
                            "command": "echo fake-command",
                            "commandActions": [],
                            "cwd": msg["params"].get("cwd", "/srv/trialogue/codex/workspace"),
                            "status": "completed" if _is_approved else "declined",
                            "exitCode": 0 if _is_approved else None,
                            "aggregatedOutput": decision,
                        },
                    },
                }
            )
            text = "FAKE_OK" if _is_approved else "FAKE_DECLINED"
            send({"method": "item/agentMessage/delta", "params": {"threadId": thread_id, "turnId": turn_id, "itemId": "msg-1", "delta": text}})
            send({"method": "item/completed", "params": {"threadId": thread_id, "turnId": turn_id, "item": {"id": "msg-1", "type": "agentMessage", "text": text}}})
            send({"method": "turn/completed", "params": {"threadId": thread_id, "turn": {"id": turn_id, "status": "completed", "items": []}}})
        else:
            send({"id": msg.get("id", 0), "result": {}})


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        handle_version()
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "app-server":
        handle_app_server()
        return 0
    print("fake-codex: unsupported args", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
