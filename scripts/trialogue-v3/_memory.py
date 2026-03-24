#!/usr/bin/env python3
"""
Trialogue v2 — 记忆注入模块（只读）

职责：
  1. 按 target 读取对应 agent 的本地记忆
  2. 过滤：只保留事实层（user/project/reference），跳过行为层（feedback）
  3. 从 user 类型记忆中剔除行为约束条目
  4. 生成注入前缀 + 审计元数据

硬规则：
  - Claude 只读 Claude 的记忆
  - Codex 只读 Codex 的记忆
  - 只读，不写，不改，不删
  - cwd 里零记忆文件
"""

import datetime
import hashlib
import json
import os
import re
import shutil
import tempfile

# ── 记忆源路径 ──

# Claude auto-memory: ~/.claude/projects/<cwd-slug>/memory/
# 需要传入 cwd 来构建路径（注意：群聊 cwd 可能和记忆积累时的 cwd 不同）
CLAUDE_MEMORY_BASE = os.path.expanduser("~/.claude/projects")

# Claude 记忆积累时的原始 cwd（群聊 cwd 是 /home/administrator/trialogue，
# 但记忆是在 /mnt/c/Users/Administrator 积累的）
# 可通过环境变量 TRIALOGUE_CLAUDE_MEMORY_CWD 覆盖
CLAUDE_MEMORY_CWD = os.environ.get(
    "TRIALOGUE_CLAUDE_MEMORY_CWD",
    "/mnt/c/Users/Administrator",
)

TRIALOGUE_WORKSPACE = os.environ.get("TRIALOGUE_WORKSPACE", "/home/administrator/trialogue")

# Codex 可信事实源：不直接注入；每次调用前先生成净化后的 live mirror。
CODEX_MEMORY_SOURCE_DIR = os.environ.get(
    "TRIALOGUE_CODEX_MEMORY_SOURCE_DIR",
    "/home/administrator/.codex-facts",
)
CODEX_MEMORY_LIVE_DIR = os.environ.get(
    "TRIALOGUE_CODEX_MEMORY_LIVE_DIR",
    os.path.join(TRIALOGUE_WORKSPACE, "state", "codex-memory-live"),
)

# ── 过滤规则 ──

# frontmatter 中的 type 字段
_TYPE_RE = re.compile(r"^type:\s*(\S+)", re.MULTILINE)
_TARGETS_RE = re.compile(r"^targets:\s*(.+)$", re.MULTILINE)
# frontmatter 边界
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# 行为层关键词：出现在正文中说明这行是行为约束，不是事实
# 对所有 type 生效（user/project/reference 都要过滤）
_BEHAVIOR_KEYWORDS = [
    # Claude 行为约束
    "must reference current code lines",
    "must be verifiable with one-line commands",
    "forbidden pseudo-completion",
    "grep-verifiable canaries",
    "expects forbidden pseudo-completion states",
    "code-level canary conditions",
    # 流程/审查指导（不是事实，是"该怎么做"）
    "what to do when conversation resumes",
    "avoid re-litigating",
    "review it under",
    "ask the user to paste",
    "my latest response agreed",
    "the first useful action is",
    # 通用行为指令模式
    "how to apply:",
]


def _parse_targets(raw_value):
    targets = []
    for part in (raw_value or "").split(","):
        token = part.strip().lower()
        if token:
            targets.append(token)
    return targets


def _parse_memory_file(path):
    """解析单个记忆文件，返回 (meta, body) 或 None。"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except (FileNotFoundError, PermissionError):
        return None

    # 提取 frontmatter type
    meta = {"type": "", "targets": []}
    fm_match = _FRONTMATTER_RE.match(content)
    if fm_match:
        frontmatter = fm_match.group(1)
        type_match = _TYPE_RE.search(frontmatter)
        if type_match:
            meta["type"] = type_match.group(1).strip()
        targets_match = _TARGETS_RE.search(frontmatter)
        if targets_match:
            meta["targets"] = _parse_targets(targets_match.group(1))

    # 提取正文（frontmatter 之后）
    if fm_match:
        body = content[fm_match.end():].strip()
    else:
        body = content.strip()

    return meta, body


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (FileNotFoundError, PermissionError):
        return ""


# 白名单：只有这些 type 才算事实层，其他一律跳过
_FACT_TYPES = {"user", "project", "reference"}

# Codex 记忆没有 frontmatter，需要额外的行为层关键词检测
_CODEX_BEHAVIOR_KEYWORDS = [
    "what to do when conversation resumes",
    "avoid re-litigating",
    "review it under",
    "canary constraints",
    "ask the user to paste",
    "my latest response agreed",
]


def _is_fact_content(mem_type, body):
    """判断是否为事实层内容。白名单模式。"""
    # feedback 类型整个跳过
    if mem_type == "feedback":
        return False

    # 有 frontmatter 的文件：只允许白名单类型
    if mem_type:
        return mem_type in _FACT_TYPES

    # 没有 frontmatter/type 的文件（如 Codex 记忆）：
    # 需要检查正文是否含行为/流程指导内容
    # 保守策略：没有 type 标记的文件默认跳过
    return False


def _matches_target_scope(targets, target_name):
    if not targets:
        return True

    normalized = set(targets)
    current_target = (target_name or "meeting").strip().lower() or "meeting"
    if "*" in normalized or "all" in normalized or "any" in normalized:
        return True
    return current_target in normalized


def _filter_behavior_lines(body):
    """从任何记忆正文中剔除行为约束行，只保留事实。

    对所有 type 生效：user / project / reference 都过滤。
    """
    lines = body.split("\n")
    filtered = []
    for line in lines:
        lower = line.lower()
        if any(kw.lower() in lower for kw in _BEHAVIOR_KEYWORDS):
            continue
        filtered.append(line)
    return "\n".join(filtered).strip()


def _build_live_memory_content(source_text, filtered_body):
    fm_match = _FRONTMATTER_RE.match(source_text)
    if not fm_match:
        return filtered_body
    return source_text[:fm_match.end()] + filtered_body.strip() + "\n"


def sync_codex_memory_live():
    """从可信事实源生成 Codex 可读的净化 live mirror。"""
    if not os.path.isdir(CODEX_MEMORY_SOURCE_DIR):
        return {"generated_at": "", "source_files": [], "live_files": []}

    os.makedirs(os.path.dirname(CODEX_MEMORY_LIVE_DIR), exist_ok=True)
    tmp_dir = tempfile.mkdtemp(
        prefix="codex-memory-live-",
        dir=os.path.dirname(CODEX_MEMORY_LIVE_DIR),
    )
    manifest_entries = []
    live_files = []
    generated_at = ""
    try:
        for name in sorted(os.listdir(CODEX_MEMORY_SOURCE_DIR)):
            if not name.endswith(".md"):
                continue
            src_path = os.path.join(CODEX_MEMORY_SOURCE_DIR, name)
            if not os.path.isfile(src_path):
                continue

            parsed = _parse_memory_file(src_path)
            if parsed is None:
                continue
            mem_meta, body = parsed
            if not _is_fact_content(mem_meta["type"], body):
                continue

            filtered_body = _filter_behavior_lines(body)
            if not filtered_body:
                continue

            source_text = _read_text(src_path)
            live_text = _build_live_memory_content(source_text, filtered_body)
            live_path = os.path.join(tmp_dir, name)
            with open(live_path, "w", encoding="utf-8") as f:
                f.write(live_text)

            source_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
            live_sha256 = hashlib.sha256(live_text.encode("utf-8")).hexdigest()
            manifest_entries.append(
                {
                    "file": name,
                    "source_file": src_path,
                    "source_sha256": source_sha256,
                    "live_file": os.path.join(CODEX_MEMORY_LIVE_DIR, name),
                    "live_sha256": live_sha256,
                    "bytes": len(live_text.encode("utf-8")),
                }
            )
            live_files.append(os.path.join(CODEX_MEMORY_LIVE_DIR, name))

        generated_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds")
        with open(os.path.join(tmp_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "generated_at": generated_at,
                    "source_dir": CODEX_MEMORY_SOURCE_DIR,
                    "live_dir": CODEX_MEMORY_LIVE_DIR,
                    "entries": manifest_entries,
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

        old_dir = CODEX_MEMORY_LIVE_DIR + ".old"
        if os.path.isdir(old_dir):
            shutil.rmtree(old_dir)
        if os.path.isdir(CODEX_MEMORY_LIVE_DIR):
            os.replace(CODEX_MEMORY_LIVE_DIR, old_dir)
        os.replace(tmp_dir, CODEX_MEMORY_LIVE_DIR)
        tmp_dir = ""
        if os.path.isdir(old_dir):
            shutil.rmtree(old_dir)
    finally:
        if tmp_dir and os.path.isdir(tmp_dir):
            shutil.rmtree(tmp_dir)

    return {
        "generated_at": generated_at,
        "source_files": [entry["source_file"] for entry in manifest_entries],
        "live_files": live_files,
    }


def _get_claude_memory_dir(cwd=None):
    """根据 cwd 构建 Claude auto-memory 目录路径。"""
    if cwd is None:
        cwd = os.getcwd()
    # Claude CLI 用 cwd 路径的 slug 作为子目录名
    # /home/administrator/trialogue → -home-administrator-trialogue
    slug = cwd.replace("/", "-")
    if not slug.startswith("-"):
        slug = "-" + slug
    mem_dir = os.path.join(CLAUDE_MEMORY_BASE, slug, "memory")
    if os.path.isdir(mem_dir):
        return mem_dir
    # 回退：尝试不带前缀 -
    mem_dir2 = os.path.join(CLAUDE_MEMORY_BASE, slug.lstrip("-"), "memory")
    if os.path.isdir(mem_dir2):
        return mem_dir2
    return mem_dir  # 返回原始路径，调用方会检查存在性


def load_memory(target, cwd=None, target_name="meeting"):
    """加载指定 agent 的事实层记忆。

    返回 dict:
        injected: bool — 是否有内容注入
        profile: str — 记忆配置名（claude_local_facts / codex_local_facts / none）
        files: list[str] — 实际读取的文件路径列表
        sha256: str — 注入内容的 sha256
        bytes: int — 注入内容的字节数
        text: str — 拼好的注入文本（纯事实）
    """
    result = {
        "injected": False,
        "profile": "none",
        "files": [],
        "source_files": [],
        "sha256": "",
        "bytes": 0,
        "text": "",
        "mirror_generated_at": "",
    }

    if target == "claude":
        mem_dir = _get_claude_memory_dir(cwd or CLAUDE_MEMORY_CWD)
        result["profile"] = "claude_local_facts"
    elif target == "codex":
        sync_info = sync_codex_memory_live()
        mem_dir = CODEX_MEMORY_LIVE_DIR
        result["profile"] = "codex_local_facts"
        result["source_files"] = sync_info["source_files"]
        result["mirror_generated_at"] = sync_info["generated_at"]
    else:
        return result

    if not os.path.isdir(mem_dir):
        result["profile"] = "none"
        return result

    # 收集所有 .md 文件（排除 MEMORY.md 索引文件）
    facts = []
    files_read = []
    source_files_read = []
    try:
        for name in sorted(os.listdir(mem_dir)):
            if not name.endswith(".md"):
                continue
            if name.upper() == "MEMORY.MD":
                continue
            path = os.path.join(mem_dir, name)
            if not os.path.isfile(path):
                continue

            parsed = _parse_memory_file(path)
            if parsed is None:
                continue

            mem_meta, body = parsed
            if not _is_fact_content(mem_meta["type"], body):
                continue

            if target == "codex" and not _matches_target_scope(mem_meta["targets"], target_name):
                continue

            # 所有类型都过滤行为约束行
            body = _filter_behavior_lines(body)

            if body:
                facts.append(body)
                files_read.append(os.path.basename(path))
                source_files_read.append(path)
    except (PermissionError, OSError):
        pass

    if not facts:
        result["profile"] = "none"
        return result

    text = "\n\n".join(facts)
    text_bytes = text.encode("utf-8")

    result["injected"] = True
    result["files"] = files_read
    if target == "claude":
        result["source_files"] = source_files_read
    result["sha256"] = hashlib.sha256(text_bytes).hexdigest()
    result["bytes"] = len(text_bytes)
    result["text"] = text
    return result


def build_injected_message(memory_result, wrapped_message):
    """把记忆前缀拼到审计头+用户消息前面。

    消息结构：
      [MEMORY-CONTEXT readonly=true profile=xxx sha256=xxx]
      (事实内容)
      [/MEMORY-CONTEXT]
      [TRIALOGUE-AUDIT rid=... nonce=... sha256=...]
      (用户消息)
    """
    if not memory_result["injected"]:
        return wrapped_message

    files_str = ",".join(os.path.basename(path) for path in memory_result["files"])
    prefix = (
        f"[MEMORY-CONTEXT readonly=true profile={memory_result['profile']}"
        f" sha256={memory_result['sha256']}"
        f" files={files_str}]\n"
        f"{memory_result['text']}\n"
        f"[/MEMORY-CONTEXT]\n"
    )
    return prefix + wrapped_message
