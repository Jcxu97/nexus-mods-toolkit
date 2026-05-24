"""Internal browser-harness helpers.

Centralizes how this package talks to Chrome via the second-window agent tab.
"""
from __future__ import annotations

import time
from typing import Any

from browser_harness.second_window import (
    ensure_agent_tab,
    evaluate_agent,
    find_agent_tab,
    navigate_agent,
)


def open_or_reuse_tab(url_substring: str | None = None, *, label: str | None = None) -> dict:
    """Return an agent tab handle. Reuses an existing one if its URL matches."""
    if url_substring:
        try:
            return find_agent_tab(url_substring)
        except Exception:
            pass
    return ensure_agent_tab(label=label) if label else ensure_agent_tab()


def navigate(tab: dict, url: str, *, settle: float = 3.0) -> None:
    navigate_agent(tab, url)
    if settle:
        time.sleep(settle)


def js(tab: dict, script: str) -> Any:
    """Evaluate JS in the agent tab. Returns the JSON-parsed value or None."""
    return evaluate_agent(tab, script)


def wait_for(tab: dict, predicate_js: str, *, timeout: float = 10.0, poll: float = 0.5) -> bool:
    """Poll a JS predicate until it returns truthy or we time out.

    The predicate must be a JS expression that evaluates to a boolean.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = evaluate_agent(tab, f"(() => {{ try {{ return Boolean({predicate_js}); }} catch(_){{ return false; }} }})()")
            if r in (True, "true"):
                return True
        except Exception:
            pass
        time.sleep(poll)
    return False
