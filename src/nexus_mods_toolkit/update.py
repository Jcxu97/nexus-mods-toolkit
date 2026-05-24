"""Push a new file version to a mod that already exists on Nexus.

Two strategies for pushing an update:

- **Update existing**: replaces an old main file. Works on the first update,
  but Nexus's backend has a bug that produces duplicate file entries on
  later updates — the dropdown shows two identical "Mod V2.x.x.x" rows and
  React's selection refuses to commit.
- **Add as new file**: skips the existing-file picker and stages the new
  upload directly. Always works, at the cost of leaving old versions in
  the file list (which Nexus's mod page already orders by date desc, so
  users see the new version first anyway).

This module exposes :func:`add_new_file_version`, which uses the safe path.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from ._browser import js, navigate, open_or_reuse_tab, wait_for


def add_new_file_version(
    mod_id: int,
    file_path: str | Path,
    *,
    version: str,
    display_name: str,
    changelog: str = "",
    category: str = "Main",
    game: str = "baldursgate3",
) -> None:
    """Drop a new file into a mod's Files tab as a brand-new entry.

    The new file lands at the top of the public mod page (date-desc
    ordering) so users see it as the latest version. Old files stay in
    the list — clean them up manually with `Set as default` + `Archive`
    after you've verified the new file works in-game.
    """
    p = Path(file_path)
    tab = open_or_reuse_tab(f"/{game}/mods/{mod_id}")
    navigate(tab, f"https://www.nexusmods.com/games/{game}/mods/{mod_id}/edit/files", settle=2)

    # Drop the archive — same flow as a new mod's first file.
    b64 = base64.b64encode(p.read_bytes()).decode()
    ok = js(tab, _DROP_ARCHIVE_JS(b64, p.name))
    if not ok:
        raise RuntimeError("No archive file input on Files tab.")

    if not wait_for(tab, "document.getElementById('file-version')", timeout=10):
        raise RuntimeError("File staging form did not appear after upload.")

    # Pick `Add as new file` if the radio is present (it isn't on the very
    # first upload — there is no existing file to replace, so the picker
    # doesn't render).
    js(tab, """
    (() => {
      const r = [...document.querySelectorAll('[role=radio]')].find(s => /^add as new file/i.test(s.textContent.trim()));
      if (r && r.getAttribute('aria-checked') !== 'true') r.click();
      return 'ok';
    })()
    """)

    js(tab, _SET_REACT_INPUT_BY_ID(("file-version", version)))
    js(tab, _SET_REACT_INPUT_BY_ID(("display-name", display_name)))
    if changelog:
        js(tab, f"""
        (() => {{
          const t = [...document.querySelectorAll('textarea')].find(t => /changelog|change log|new in this version/i.test(t.placeholder || t.name || t.id || ''));
          if (!t) return false;
          const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(t), 'value').set;
          setter.call(t, {json.dumps(changelog)});
          t.dispatchEvent(new Event('input', {{bubbles: true}}));
          t.dispatchEvent(new Event('change', {{bubbles: true}}));
          return true;
        }})()
        """)

    # Category panel.
    js(tab, f"""
    (() => {{
      const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === {json.dumps(category)});
      if (b && b.getAttribute('aria-selected') !== 'true') b.click();
      return 'ok';
    }})()
    """)

    time.sleep(0.4)
    js(tab, "(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Save file' && !b.disabled); if (b) { b.scrollIntoView({block:'center'}); b.click(); } return 'ok'; })()")
    if not wait_for(tab, f"!document.getElementById('file-version') && [...document.querySelectorAll('*')].some(e => e.textContent.includes({json.dumps(display_name)}))", timeout=60):
        raise RuntimeError("File did not land in the file list after `Save file`.")


# ---- helpers (kept private; the public API is just add_new_file_version) ----

def _DROP_ARCHIVE_JS(b64: str, name: str) -> str:
    return (
        "(() => {"
        f" const b64 = {json.dumps(b64)};"
        f" const name = {json.dumps(name)};"
        " const bin = atob(b64);"
        " const arr = new Uint8Array(bin.length);"
        " for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);"
        " const file = new File([arr], name, {type: 'application/zip'});"
        " const inputs = [...document.querySelectorAll('input[type=file]')].filter(i => /zip|rar|7z/.test(i.accept || ''));"
        " if (!inputs.length) return false;"
        " const inp = inputs[0];"
        " const dt = new DataTransfer();"
        " dt.items.add(file);"
        " inp.files = dt.files;"
        " inp.dispatchEvent(new Event('change', {bubbles: true}));"
        " inp.dispatchEvent(new Event('input', {bubbles: true}));"
        " return true;"
        "})()"
    )


def _SET_REACT_INPUT_BY_ID(pair: tuple[str, str]) -> str:
    elt_id, value = pair
    return (
        "(() => {"
        f" const el = document.getElementById({json.dumps(elt_id)});"
        " if (!el) return false;"
        " const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set;"
        f" setter.call(el, {json.dumps(value)});"
        " el.dispatchEvent(new Event('input', {bubbles: true}));"
        " el.dispatchEvent(new Event('change', {bubbles: true}));"
        " return true;"
        "})()"
    )
