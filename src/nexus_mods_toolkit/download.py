"""Download a single Nexus mod file via the slow-download flow.

Why we don't use the public API for the file bytes
--------------------------------------------------

The Nexus REST API endpoint ``/games/{game}/mods/{mod_id}/files/{file_id}/download_link.json``
returns a signed CDN URL — but only for **Premium** accounts. Free accounts
get HTTP 403.

What still works for free accounts: the user-facing **Slow download** button
on the mod's Files tab calls a private endpoint that returns the same kind
of signed CDN URL with embedded `md5`, `expires`, and `user_id` tokens. The
URL is self-authenticating (no cookies needed at fetch time), so once we
capture it we can hand it off to any HTTP client.

The capture pattern:

1. Open the mod page at ``?tab=files&file_id=<id>`` in browser-harness.
2. JS-click the ``Slow download`` button.
3. Listen for ``Page.downloadWillBegin`` over CDP — its ``params.url`` is
   the signed URL.
4. Fetch the URL with ``urllib`` and write to disk.

This avoids letting Chrome's download manager handle the file (it tends to
silently cancel downloads in offscreen agent windows).
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from browser_harness.helpers import cdp, drain_events
from browser_harness.second_window import ensure_agent_tab

API_BASE = "https://api.nexusmods.com/v1"
DEFAULT_USER_AGENT = "nexus-mods-toolkit/0.1"
API_KEY_FILE = Path.home() / ".nexus-api-key"


def download_mod(
    mod_id: int,
    *,
    file_id: int | None = None,
    dest_dir: str | Path | None = None,
    game: str = "baldursgate3",
    api_key: str | None = None,
    timeout: float = 60.0,
) -> Path:
    """Download a mod's main file (or a specific ``file_id``) to ``dest_dir``.

    If ``file_id`` is omitted, the latest primary main file is resolved
    via the public Nexus API. The API call only needs the mod's metadata —
    it does NOT need a Premium subscription. The actual download bytes go
    through the Slow-download flow (free-tier compatible).

    Returns the local Path of the downloaded file.
    """
    out_dir = Path(dest_dir) if dest_dir else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    if file_id is None:
        key = api_key or _resolve_api_key()
        meta = _api_get(f"/games/{game}/mods/{mod_id}.json", key)
        files = _api_get(f"/games/{game}/mods/{mod_id}/files.json?category=main", key).get("files", [])
        if not files:
            raise RuntimeError(f"Mod {mod_id} has no main files on Nexus.")
        primary = next((f for f in files if f.get("is_primary")), None)
        chosen = primary or max(files, key=lambda f: f.get("uploaded_timestamp", 0))
        file_id = int(chosen["file_id"])
        suggested_ext = ".zip"
        nice_name = _safe(meta.get("name", str(mod_id)))
        version = str(meta.get("version", "x"))
    else:
        suggested_ext = ".zip"
        nice_name = str(mod_id)
        version = "x"

    dl_url, dl_name = _capture_signed_url(mod_id, file_id, game=game, timeout=timeout)
    suffix = Path(dl_name).suffix or suggested_ext
    target = out_dir / f"{mod_id}_{nice_name}_v{version}{suffix}"
    _http_download(dl_url, target)
    return target


# ---- internals -----------------------------------------------------------

def _capture_signed_url(mod_id: int, file_id: int, *, game: str, timeout: float) -> tuple[str, str]:
    """Drive the user's Chrome to click `Slow download` and capture the signed URL."""
    tid = ensure_agent_tab()
    sid = cdp("Target.attachToTarget", targetId=tid, flatten=True)["sessionId"]
    page_url = f"https://www.nexusmods.com/{game}/mods/{mod_id}?tab=files&file_id={file_id}"
    try:
        cdp("Page.enable", session_id=sid)
        cdp("Page.navigate", session_id=sid, url=page_url)
        deadline = time.time() + 15
        while time.time() < deadline:
            r = cdp("Runtime.evaluate", session_id=sid, expression="document.readyState")
            if r.get("result", {}).get("value") == "complete":
                break
            time.sleep(0.3)
        time.sleep(3)
        drain_events()

        click_js = """
(function() {
    function walk(root, hits) {
        const tw = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
        let n;
        while ((n = tw.nextNode())) {
            const t = (n.textContent || "").trim();
            if (n.tagName === "BUTTON" && t === "Slow download") hits.push(n);
            if (n.shadowRoot) walk(n.shadowRoot, hits);
        }
    }
    const hits = [];
    walk(document, hits);
    if (!hits.length) return "NOT_FOUND";
    hits[0].scrollIntoView({block: "center"});
    hits[0].click();
    return "clicked";
})()
"""
        r = cdp("Runtime.evaluate", session_id=sid, expression=click_js, returnByValue=True)
        if r.get("result", {}).get("value") != "clicked":
            raise RuntimeError("Slow download button not found — premium-only mod, or login expired.")

        deadline = time.time() + timeout
        while time.time() < deadline:
            time.sleep(0.25)
            for ev in drain_events():
                if ev.get("session_id") != sid:
                    continue
                if ev.get("method") == "Page.downloadWillBegin":
                    p = ev["params"]
                    return p["url"], p.get("suggestedFilename", "")
        raise RuntimeError("Page.downloadWillBegin did not fire — the click may have been silently rejected.")
    finally:
        try:
            cdp("Target.detachFromTarget", sessionId=sid)
        except Exception:
            pass


def _http_download(url: str, target: Path) -> None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) {DEFAULT_USER_AGENT}",
        },
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        with open(target, "wb") as f:
            shutil.copyfileobj(resp, f)


def _api_get(path: str, api_key: str, timeout: int = 30):
    req = urllib.request.Request(
        API_BASE + path,
        headers={
            "apikey": api_key,
            "accept": "application/json",
            "user-agent": DEFAULT_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {e.code} on {path}: {body}") from e


def _resolve_api_key() -> str:
    key = (os.environ.get("NEXUS_API_KEY") or "").strip()
    if key:
        return key
    if API_KEY_FILE.exists():
        return API_KEY_FILE.read_text(encoding="utf-8").strip()
    msg = (
        "Nexus API key not found. Set NEXUS_API_KEY or write your personal key to "
        f"{API_KEY_FILE}. Generate one at https://www.nexusmods.com/users/myaccount?tab=api%20access"
    )
    print("ERROR: " + msg, file=sys.stderr)
    raise RuntimeError(msg)


def _safe(s: str) -> str:
    out = "".join(c if c.isalnum() or c in "-_." else "_" for c in (s or "mod"))
    return out[:80] or "mod"
