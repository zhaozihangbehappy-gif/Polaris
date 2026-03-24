#!/usr/bin/env python3
"""Trialogue v4 — 7-step ingestion pipeline.

Fetches external content, converts to plain text, sanitizes, tags source,
records audit summary, and returns cleaned content.

Usage (CLI fallback mode):
    python3 pipeline.py fetch <url>
    python3 pipeline.py search <query>
    python3 pipeline.py sanitize < file.txt
"""
from __future__ import annotations

import hashlib
import html.parser
import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

# Import sanitizer from local hardening.py
from hardening import (
    DEFAULT_SANITIZER_PATTERNS,
    _sanitize_text_once,
    load_sanitizer_patterns,
)

# Lazy-import audit to avoid circular imports at module load
_audit_mod = None


def _get_audit():
    global _audit_mod
    if _audit_mod is None:
        import audit as _a
        _audit_mod = _a
    return _audit_mod

# ── Configuration ───────────────────────────────────────────────────────────

from config import get_conf, get_int

_conf = get_conf()
MAX_RESPONSE_BYTES = get_int(_conf, "max_response_bytes", 512 * 1024)
DEFAULT_TIMEOUT = get_int(_conf, "default_timeout", 15)
USER_AGENT = "trialogue-v4/1.0 (content-sanitizer)"


# ── Step 2: HTML → plain text ──────────────────────────────────────────────

class _HTMLStripper(html.parser.HTMLParser):
    """Strip HTML tags, preserving text content."""

    _DISCARD_TAGS = frozenset({"script", "style", "noscript"})
    _BLOCK_TAGS = frozenset({
        "p", "br", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6",
        "tr", "blockquote", "hr", "section", "article", "header", "footer",
    })
    _PRE_TAGS = frozenset({"pre", "code"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._discard_depth = 0
        self._pre_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._DISCARD_TAGS:
            self._discard_depth += 1
            return
        if self._discard_depth > 0:
            return
        if tag_lower in self._PRE_TAGS:
            self._pre_depth += 1
        if tag_lower in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if tag_lower in self._DISCARD_TAGS:
            self._discard_depth = max(0, self._discard_depth - 1)
            return
        if self._discard_depth > 0:
            return
        if tag_lower in self._PRE_TAGS:
            self._pre_depth = max(0, self._pre_depth - 1)
        if tag_lower in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._discard_depth > 0:
            return
        if self._pre_depth > 0:
            # Preserve original formatting inside <pre>/<code>
            self._parts.append(data)
        else:
            self._parts.append(data)

    def get_text(self) -> str:
        text = "".join(self._parts)
        # Collapse 3+ newlines but preserve double newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def html_to_text(html_content: str) -> str:
    """Convert HTML to plain text."""
    stripper = _HTMLStripper()
    try:
        stripper.feed(html_content)
    except Exception:
        # Fallback: strip tags with regex
        text = re.sub(r"<[^>]+>", " ", html_content)
        return re.sub(r"\s+", " ", text).strip()
    return stripper.get_text()


# ── Step 1: Fetch content ──────────────────────────────────────────────────

def fetch_url(url: str, *, timeout: int = DEFAULT_TIMEOUT,
              max_bytes: int = MAX_RESPONSE_BYTES) -> tuple[str, str]:
    """Fetch URL and return (raw_text, content_type).

    Raises on network errors, binary content, or oversized responses.
    """
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    resp = urllib.request.urlopen(req, timeout=timeout)

    content_type = resp.headers.get("Content-Type", "")
    # Reject binary content
    if content_type and not any(
        t in content_type.lower()
        for t in ("text/", "application/json", "application/xml", "application/xhtml")
    ):
        raise ValueError(
            f"Non-text content type: {content_type}. "
            "Only text and HTML content is supported."
        )

    raw_bytes = resp.read(max_bytes + 1)
    if len(raw_bytes) > max_bytes:
        raw_bytes = raw_bytes[:max_bytes]

    # Force UTF-8 decode
    raw_text = raw_bytes.decode("utf-8", errors="replace")
    return raw_text, content_type


# ── Step 3-7: Full pipeline ────────────────────────────────────────────────

def ingest(
    raw_text: str,
    *,
    source_type: str = "fetch",
    source_url: str = "",
    content_type: str = "",
    patterns: dict[str, Any] | None = None,
    via_guard: bool = True,
) -> dict[str, Any]:
    """Run the full 7-step ingestion pipeline on raw text.

    Returns dict with cleaned text, audit metadata, and modification details.
    """
    if patterns is None:
        patterns = dict(DEFAULT_SANITIZER_PATTERNS)

    # Step 2: HTML → plain text (if HTML)
    is_html = (
        "html" in content_type.lower()
        or raw_text.lstrip()[:15].lower().startswith(("<!doctype", "<html", "<head"))
    )
    if is_html:
        plain_text = html_to_text(raw_text)
    else:
        plain_text = raw_text

    # Step 1 hash (on the text that enters the sanitizer)
    raw_sha256 = hashlib.sha256(plain_text.encode("utf-8")).hexdigest()

    # Step 3: Sanitize
    cleaned, modifications, removed = _sanitize_text_once(plain_text, patterns)

    # Step 4: Source tag + Step 5: Audit summary
    cleaned_sha256 = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return {
        "cleaned_text": cleaned,
        "source_type": source_type,
        "source_url": source_url,
        "fetched_at": timestamp,
        "raw_sha256": raw_sha256,
        "cleaned_sha256": cleaned_sha256,
        "modifications": modifications,
        "removed": removed,
        "mode": "strict",
        "via_guard": via_guard,
        "is_html": is_html,
    }


def pipeline_fetch(url: str, *, patterns: dict[str, Any] | None = None,
                   via_guard: bool = True) -> dict[str, Any]:
    """Fetch URL and run through full pipeline."""
    raw_text, content_type = fetch_url(url)
    result = ingest(
        raw_text,
        source_type="fetch",
        source_url=url,
        content_type=content_type,
        patterns=patterns,
        via_guard=via_guard,
    )
    # Append to audit chain
    result = _audit_wrap(result)
    return result


def _audit_wrap(result: dict[str, Any]) -> dict[str, Any]:
    """Append to audit chain and handle strict/local/disabled modes.

    - disabled: skip audit entirely
    - local: best-effort — failure surfaces metadata but returns content
    - strict: failure blocks pipeline — cleaned_text removed, error returned
    """
    audit_conf = get_conf().get("audit_mode", "local")
    if audit_conf == "disabled":
        result["audit_status"] = "disabled"
        return result

    try:
        chain_result = _get_audit().append_ingestion_chain(result)
        result["audit_status"] = "ok"
        result["audit_seq"] = chain_result.get("seq", 0)
        # Remote anchor publish (if configured)
        anchor_sink = get_conf().get("remote_anchor_sink", "")
        anchor_interval = int(get_conf().get("remote_anchor_interval", "0") or "0")
        if anchor_sink and (anchor_interval <= 0 or result["audit_seq"] % anchor_interval == 0):
            try:
                anchor_result = _get_audit().publish_ingestion_anchor()
                if anchor_result.get("ok"):
                    result["anchor_status"] = "ok"
                else:
                    err = anchor_result.get(
                        "error", anchor_result.get("publish", {}).get("error", "unknown")
                    )
                    result["anchor_status"] = "failed"
                    result["anchor_error"] = err
                    if audit_conf == "strict":
                        result["cleaned_text"] = ""
                        result["error"] = f"anchor publish failed (strict mode): {err}"
                        print(f"[trialogue-guard] ANCHOR STRICT FAILURE — content blocked: {err}", file=sys.stderr)
            except Exception as ae:
                result["anchor_status"] = "failed"
                result["anchor_error"] = str(ae)
                if audit_conf == "strict":
                    result["cleaned_text"] = ""
                    result["error"] = f"anchor publish failed (strict mode): {ae}"
                    print(f"[trialogue-guard] ANCHOR STRICT FAILURE — content blocked: {ae}", file=sys.stderr)
    except Exception as e:
        if audit_conf == "strict":
            # Strict mode: audit failure blocks the pipeline
            result["audit_status"] = "failed"
            result["audit_error"] = str(e)
            result["cleaned_text"] = ""
            result["error"] = f"audit chain write failed (strict mode): {e}"
            print(f"[trialogue-guard] AUDIT STRICT FAILURE — content blocked: {e}", file=sys.stderr)
        else:
            # Local mode: best-effort — surface failure but return content
            result["audit_status"] = "failed"
            result["audit_error"] = str(e)
            print(f"[trialogue-guard] AUDIT CHAIN FAILURE: {e}", file=sys.stderr)
    return result


def pipeline_search(query: str, *, search_endpoint: str | None = None,
                    patterns: dict[str, Any] | None = None,
                    via_guard: bool = True) -> dict[str, Any]:
    """Search and return sanitized results.

    If no search endpoint is configured (neither param nor conf), returns a
    message prompting the user to provide a URL directly.
    """
    if search_endpoint is None:
        search_endpoint = get_conf().get("search_endpoint", "")
    if not search_endpoint:
        return {
            "cleaned_text": (
                f"No search endpoint configured. "
                f"Please provide a URL directly using trialogue_fetch.\n"
                f"Original query: {query}"
            ),
            "source_type": "search",
            "source_url": "",
            "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "raw_sha256": "",
            "cleaned_sha256": "",
            "modifications": 0,
            "removed": [],
            "mode": "strict",
            "via_guard": via_guard,
            "is_html": False,
        }

    # Fetch search results
    search_url = f"{search_endpoint}?q={urllib.parse.quote(query)}"
    raw_text, content_type = fetch_url(search_url)
    result = ingest(
        raw_text,
        source_type="search",
        source_url=search_url,
        content_type=content_type,
        patterns=patterns,
        via_guard=via_guard,
    )
    result = _audit_wrap(result)
    return result


def pipeline_sanitize(text: str, *, mode: str = "strict",
                      patterns: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sanitize arbitrary text (no fetch, no HTML conversion)."""
    if patterns is None:
        patterns = dict(DEFAULT_SANITIZER_PATTERNS)
    cleaned, modifications, removed = _sanitize_text_once(text, patterns)
    return {
        "cleaned_text": cleaned if mode == "strict" else text,
        "source_type": "sanitize",
        "source_url": "",
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "raw_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "cleaned_sha256": hashlib.sha256(cleaned.encode("utf-8")).hexdigest(),
        "modifications": modifications,
        "removed": removed,
        "mode": mode,
        "via_guard": False,
        "is_html": False,
    }


# ── CLI fallback mode ──────────────────────────────────────────────────────

def _cli_main() -> int:
    if len(sys.argv) < 2:
        print("Usage: pipeline.py fetch <url> | search <query> | sanitize", file=sys.stderr)
        return 2

    cmd = sys.argv[1]

    if cmd == "fetch":
        if len(sys.argv) < 3:
            print("Usage: pipeline.py fetch <url>", file=sys.stderr)
            return 2
        url = sys.argv[2]
        try:
            result = pipeline_fetch(url, via_guard=False)
        except Exception as e:
            print(f"pipeline: fetch error: {e}", file=sys.stderr)
            return 2
        if "--json" in sys.argv:
            print(json.dumps(result, ensure_ascii=False))
        else:
            sys.stdout.write(result["cleaned_text"])
            if result["cleaned_text"] and not result["cleaned_text"].endswith("\n"):
                sys.stdout.write("\n")
            if result["modifications"] > 0:
                print(
                    f"pipeline: {result['modifications']} modification(s), "
                    f"removed: {result['removed']}",
                    file=sys.stderr,
                )
        return 1 if result["modifications"] > 0 else 0

    if cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: pipeline.py search <query>", file=sys.stderr)
            return 2
        query = sys.argv[2]
        result = pipeline_search(query, via_guard=False)
        if "--json" in sys.argv:
            print(json.dumps(result, ensure_ascii=False))
        else:
            sys.stdout.write(result["cleaned_text"])
            if result["cleaned_text"] and not result["cleaned_text"].endswith("\n"):
                sys.stdout.write("\n")
        return 0

    if cmd == "sanitize":
        text = sys.stdin.read()
        result = pipeline_sanitize(text)
        if "--json" in sys.argv:
            print(json.dumps(result, ensure_ascii=False))
        else:
            sys.stdout.write(result["cleaned_text"])
            if result["cleaned_text"] and not result["cleaned_text"].endswith("\n"):
                sys.stdout.write("\n")
        return 1 if result["modifications"] > 0 else 0

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(_cli_main())
