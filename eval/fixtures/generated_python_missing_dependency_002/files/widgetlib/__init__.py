"""Tiny pretend dependency package with an outdated public API."""

__all__ = ["render_widget"]


def render_widget(name: str) -> str:
    return f"[{name}]"
