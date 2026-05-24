"""Upload a brand-new mod to Nexus through the 5-step draft wizard.

Validated 2026-05-24 against ``baldursgate3`` (mod 23045). The same 5-step
wizard is used for every Nexus game, so this module should work for Skyrim,
Fallout 4, etc. with no changes — the only game-specific bit is the
``game`` slug in :func:`create_draft`.

The flow follows §11 of the BG3-LLM-WIKI Nexus playbook:

1. Open ``/games/<game>`` in the browser. Click ``Upload``, then
   ``Upload mod`` in the dropdown — both are ``<button>`` (not ``<a>``).
2. Fill the 4-field draft modal (name, short description, game prefilled,
   category) and click ``Create draft``. Page redirects to
   ``/games/<game>/mods/<id>/edit/general``.
3. Fill the General tab (full description in SCEditor BBCode mode + tags +
   author + version), then click the bottom Save button (the top sticky one
   stays disabled until React's dirty tracker fires).
4. Media tab: drop a header (optional) and at least one gallery image
   (required). Header opens a crop dialog — confirm it.
5. Files tab: drop the .zip, set ``display-name``, set ``file-version``
   (default ``1`` is wrong, must be ``1.0.0.0``), pick category, click
   ``Save file`` (NOT the page-level Save).
6. Click the green ``Publish`` button at the top right; a dialog pops up;
   click ``Publish mod`` inside it. URL becomes ``?published=1``.
"""
from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from ._browser import js, navigate, open_or_reuse_tab, wait_for

# ---- Spec dataclasses ----------------------------------------------------

@dataclass
class FileSpec:
    """One uploadable file (a .zip / .rar / .7z) for the Files tab."""
    path: str | Path
    version: str = "1.0.0.0"
    display_name: str | None = None
    category: str = "Main"  # Main / Optional / Old / Miscellaneous / Updates
    description: str = ""


@dataclass
class ModSpec:
    """Everything you need to publish a brand-new mod page in one call."""
    name: str
    author: str
    version: str
    category: str  # e.g. "Gameplay", "Patches", "User Interface"
    short_description: str
    description_bbcode: str
    tags: tuple[str, ...] = ()
    header_image: str | Path | None = None
    gallery_images: list[str | Path] = field(default_factory=list)
    files: list[FileSpec] = field(default_factory=list)
    game: str = "baldursgate3"


# ---- High-level entry point ---------------------------------------------

def upload_mod(spec: ModSpec) -> str:
    """Run the full 6-step publish flow for a new mod. Returns the public URL.

    Requires that the user is already logged in to Nexus in the Chrome that
    browser-harness drives. Drops a single agent tab inside the user's
    second window — does not steal focus from the active tab.
    """
    if not spec.gallery_images:
        raise ValueError("ModSpec.gallery_images must contain at least one image — Nexus requires Images.")
    if not spec.files:
        raise ValueError("ModSpec.files must contain at least one file — Nexus requires Files.")

    mod_id = create_draft(
        name=spec.name,
        short_description=spec.short_description,
        category=spec.category,
        game=spec.game,
    )
    fill_general(
        mod_id,
        author=spec.author,
        version=spec.version,
        description_bbcode=spec.description_bbcode,
        tags=spec.tags,
        game=spec.game,
    )
    if spec.header_image:
        upload_image(mod_id, spec.header_image, kind="header", game=spec.game)
    for img in spec.gallery_images:
        upload_image(mod_id, img, kind="image", game=spec.game)
    for f in spec.files:
        upload_file(
            mod_id,
            f.path,
            version=f.version,
            display_name=f.display_name or f"{spec.name} v{spec.version}",
            category=f.category,
            description=f.description,
            game=spec.game,
        )
    return publish(mod_id, game=spec.game)


# ---- Step 1: create draft -----------------------------------------------

def create_draft(*, name: str, short_description: str, category: str, game: str = "baldursgate3") -> int:
    """Open the upload modal and return the new mod's numeric id."""
    _validate_mod_name(name)
    tab = open_or_reuse_tab(f"nexusmods.com/games/{game}", label=f"nexus-upload-{int(time.time())}")
    navigate(tab, f"https://www.nexusmods.com/games/{game}", settle=3)

    # Step 1: page-nav `Upload` button (BUTTON, not <a>) -> dropdown -> `Upload mod`
    js(tab, _CLICK_UPLOAD_DROPDOWN_JS)
    time.sleep(0.7)
    js(tab, _CLICK_UPLOAD_MOD_OPTION_JS)
    if not wait_for(tab, "document.querySelector('[role=dialog]')", timeout=8):
        raise RuntimeError("Upload modal did not open — confirm you are logged in to nexusmods.com.")

    # Step 2: fill the 4 fields and click Create draft
    js(tab, _SET_REACT_INPUT_BY_NAME_JS("name", name))
    js(tab, _SET_REACT_TEXTAREA_BY_NAME_JS("summary", short_description))
    _select_combobox_option(tab, placeholder_or_label_substr="Category", option_text=category)
    time.sleep(0.4)
    js(tab, "(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Create draft' && !b.disabled); if (b) b.click(); return 'ok'; })()")
    if not wait_for(tab, "/edit\\\\/general/.test(location.href)", timeout=15):
        raise RuntimeError("Did not redirect to /edit/general after Create draft.")

    m = re.search(r"/mods/(\d+)/edit/general", _current_url(tab))
    if not m:
        raise RuntimeError(f"Could not extract mod_id from URL after Create draft. URL: {_current_url(tab)}")
    return int(m.group(1))


# ---- Step 3: General tab -------------------------------------------------

def fill_general(mod_id: int, *, author: str, version: str, description_bbcode: str,
                 tags: tuple[str, ...] = (), game: str = "baldursgate3") -> None:
    """Fill in the description / version / author / tags and Save the General tab."""
    tab = open_or_reuse_tab(f"/{game}/mods/{mod_id}")
    navigate(tab, f"https://www.nexusmods.com/games/{game}/mods/{mod_id}/edit/general", settle=3)

    # Author and version are simple React inputs.
    js(tab, _SET_REACT_INPUT_BY_ID_JS("author-name", author))
    js(tab, _SET_REACT_INPUT_BY_ID_JS("version", version))

    # Description editor: SCEditor BBCode mode. Set HTML on the WYSIWYG side,
    # then call updateOriginal() to mirror the BBCode into the underlying
    # textarea (which is React-uncontrolled / `defaultValue`).
    js(tab, _SET_DESCRIPTION_BBCODE_JS(description_bbcode))

    # Tags: must click already-listed Popular Tags chips. Type-search is
    # almost always silent-fail because Nexus's tag set is small and the
    # search filter is overly strict.
    for tag in tags:
        js(tab, f"(() => {{ const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === {json.dumps(tag)}); if (b) b.click(); return 'ok'; }})()")
        time.sleep(0.2)

    # Save: there are two Save buttons. Idx 0 (top sticky) stays disabled
    # until the dirty tracker fires; idx 1 (bottom) is the one to click.
    time.sleep(0.5)
    js(tab, """
    (() => {
      const saves = [...document.querySelectorAll('button')].filter(b => b.textContent.trim() === 'Save');
      const live = saves.find(b => !b.disabled && b.offsetParent !== null);
      if (live) { live.scrollIntoView({block:'center'}); live.click(); }
      return 'ok';
    })()
    """)
    if not wait_for(tab, "![...document.querySelectorAll('a, [role=tab]')].some(e => /^[1]?General \\\\*/.test(e.textContent.trim()))", timeout=10):
        raise RuntimeError("General tab did not save — the asterisk on `1General *` did not clear.")


# ---- Step 4: Media tab --------------------------------------------------

def upload_image(mod_id: int, image_path: str | Path, *, kind: str = "image",
                 game: str = "baldursgate3") -> None:
    """Drop a single image into the Media tab.

    ``kind`` is ``"image"`` (gallery) or ``"header"``. Header opens a crop
    dialog which we automatically Confirm.
    """
    if kind not in ("image", "header"):
        raise ValueError(f"kind must be 'image' or 'header', got {kind!r}")
    tab = open_or_reuse_tab(f"/{game}/mods/{mod_id}")
    navigate(tab, f"https://www.nexusmods.com/games/{game}/mods/{mod_id}/edit/media", settle=2)

    p = Path(image_path)
    b64 = base64.b64encode(p.read_bytes()).decode()
    mime = _mime_for_image(p)

    # Inputs are listed in DOM order: [0] header, [1] gallery — when both
    # are still present. After the header is set, only the gallery input
    # remains. The kind argument tells us which one to target.
    target_index = 0 if kind == "header" else (1 if _has_two_image_inputs(tab) else 0)
    if not _drop_into_image_input(tab, b64, mime, p.name, target_index):
        raise RuntimeError(f"No {kind} input found on Media tab — wrong page state?")

    if kind == "header":
        if not wait_for(tab, "[...document.querySelectorAll('[role=dialog]')].some(d => /Adding header/i.test(d.textContent) && d.offsetParent !== null)", timeout=8):
            raise RuntimeError("Header crop dialog did not appear.")
        time.sleep(0.4)
        js(tab, "(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Confirm' && b.offsetParent !== null); if (b) b.click(); return 'ok'; })()")
        time.sleep(2.0)
    else:
        # Gallery upload is fire-and-forget — Nexus auto-saves it.
        time.sleep(2.5)


# ---- Step 5: Files tab --------------------------------------------------

def upload_file(mod_id: int, file_path: str | Path, *, version: str, display_name: str,
                category: str = "Main", description: str = "",
                game: str = "baldursgate3") -> None:
    """Upload a single .zip/.rar/.7z to the Files tab and click Save file."""
    tab = open_or_reuse_tab(f"/{game}/mods/{mod_id}")
    navigate(tab, f"https://www.nexusmods.com/games/{game}/mods/{mod_id}/edit/files", settle=2)

    p = Path(file_path)
    b64 = base64.b64encode(p.read_bytes()).decode()
    if not _drop_into_archive_input(tab, b64, p.name):
        raise RuntimeError("No archive (.zip/.rar/.7z) file input found on Files tab.")

    # Wait for Nexus's staged form to appear (display-name / file-version inputs).
    if not wait_for(tab, "document.getElementById('file-version')", timeout=10):
        raise RuntimeError("File staging form did not appear after upload.")

    js(tab, _SET_REACT_INPUT_BY_ID_JS("file-version", version))
    js(tab, _SET_REACT_INPUT_BY_ID_JS("display-name", display_name))
    if description:
        js(tab, _SET_REACT_TEXTAREA_BY_PLACEHOLDER_JS("description", description))

    # Category panel: click the matching entry if it's not already selected.
    js(tab, f"""
    (() => {{
      const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === {json.dumps(category)});
      if (b && b.getAttribute('aria-selected') !== 'true') b.click();
      return 'ok';
    }})()
    """)

    # Click `Save file` (NOT the page-level Save).
    time.sleep(0.4)
    js(tab, "(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Save file' && !b.disabled); if (b) { b.scrollIntoView({block:'center'}); b.click(); } return 'ok'; })()")
    # Wait until the staging form goes away and the file appears in the
    # list (rendered as a row containing the display name).
    if not wait_for(tab, f"!document.getElementById('file-version') && [...document.querySelectorAll('*')].some(e => e.textContent.includes({json.dumps(display_name)}))", timeout=30):
        raise RuntimeError("File did not land in the file list after `Save file`.")


# ---- Step 6: Publish -----------------------------------------------------

def publish(mod_id: int, *, game: str = "baldursgate3") -> str:
    """Click the green Publish button and confirm in the dialog. Returns the
    public mod URL with ``?published=1`` query param.
    """
    tab = open_or_reuse_tab(f"/{game}/mods/{mod_id}")

    # First click: page-level green Publish button (top right).
    js(tab, "(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Publish' && !b.disabled && b.offsetParent !== null); if (b) { b.scrollIntoView({block:'center'}); b.click(); } return 'ok'; })()")
    if not wait_for(tab, "[...document.querySelectorAll('button')].some(b => b.textContent.trim() === 'Publish mod' && !b.disabled)", timeout=8):
        raise RuntimeError("Publish confirmation dialog did not open.")

    # Second click: blue `Publish mod` button inside the dialog.
    js(tab, "(() => { const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Publish mod' && !b.disabled && b.offsetParent !== null); if (b) b.click(); return 'ok'; })()")
    if not wait_for(tab, "/published=1/.test(location.href)", timeout=15):
        raise RuntimeError("Did not see ?published=1 in URL — publish may have failed silently.")
    return _current_url(tab)


# ---- internals -----------------------------------------------------------

_ALLOWED_NAME_CHARS = re.compile(r"^[A-Za-z0-9 _'().\-]+$")

def _validate_mod_name(name: str) -> None:
    if not _ALLOWED_NAME_CHARS.match(name):
        rejected = sorted({c for c in name if not _ALLOWED_NAME_CHARS.match(c)})
        raise ValueError(
            f"Nexus rejects {''.join(rejected)!r} in mod names — only letters, "
            f"numbers, spaces, and _'().-  are allowed. Rename {name!r}."
        )


def _current_url(tab: dict) -> str:
    return js(tab, "location.href") or ""


def _has_two_image_inputs(tab: dict) -> bool:
    return bool(js(tab, "document.querySelectorAll('input[type=file][accept*=image]').length === 2"))


def _drop_into_image_input(tab: dict, b64: str, mime: str, name: str, idx: int) -> bool:
    script = (
        "(() => {"
        f" const b64 = {json.dumps(b64)};"
        f" const mime = {json.dumps(mime)};"
        f" const name = {json.dumps(name)};"
        f" const idx = {idx};"
        " const bin = atob(b64);"
        " const arr = new Uint8Array(bin.length);"
        " for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);"
        " const file = new File([arr], name, {type: mime});"
        " const inputs = [...document.querySelectorAll('input[type=file]')].filter(i => /image/.test(i.accept || ''));"
        " if (idx >= inputs.length) return false;"
        " const inp = inputs[idx];"
        " const dt = new DataTransfer();"
        " dt.items.add(file);"
        " inp.files = dt.files;"
        " inp.dispatchEvent(new Event('change', {bubbles: true}));"
        " inp.dispatchEvent(new Event('input', {bubbles: true}));"
        " return true;"
        "})()"
    )
    return bool(js(tab, script))


def _drop_into_archive_input(tab: dict, b64: str, name: str) -> bool:
    script = (
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
    return bool(js(tab, script))


def _select_combobox_option(tab: dict, *, placeholder_or_label_substr: str, option_text: str) -> None:
    script = (
        "(() => {"
        f" const needle = {json.dumps(placeholder_or_label_substr.lower())};"
        " const cb = [...document.querySelectorAll('input[role=combobox]')].find(i =>"
        "   (i.placeholder || '').toLowerCase().includes(needle) ||"
        "   (i.getAttribute('aria-label') || '').toLowerCase().includes(needle));"
        " if (!cb) return false;"
        " cb.focus();"
        " cb.click();"
        " return true;"
        "})()"
    )
    js(tab, script)
    time.sleep(0.3)
    pick = (
        "(() => {"
        f" const t = {json.dumps(option_text)};"
        " const opts = [...document.querySelectorAll('[role=option]')];"
        " const m = opts.find(o => o.textContent.trim() === t);"
        " if (!m) return false;"
        " const ev = (type) => m.dispatchEvent(new MouseEvent(type, {bubbles: true, cancelable: true, button: 0}));"
        " ev('mousedown'); ev('mouseup'); ev('click');"
        " return true;"
        "})()"
    )
    js(tab, pick)


def _mime_for_image(p: Path) -> str:
    s = p.suffix.lower()
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif"}.get(s, "image/png")


# ---- JS snippets ---------------------------------------------------------

_CLICK_UPLOAD_DROPDOWN_JS = """
(() => {
  const b = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Upload' && b.offsetParent !== null);
  if (b) b.click();
  return 'ok';
})()
"""

_CLICK_UPLOAD_MOD_OPTION_JS = """
(() => {
  const b = [...document.querySelectorAll('button')].find(b => /^Upload mod/i.test(b.textContent.trim()) && b.offsetParent !== null);
  if (b) b.click();
  return 'ok';
})()
"""


def _SET_REACT_INPUT_BY_ID_JS(elt_id: str, value: str) -> str:
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


def _SET_REACT_INPUT_BY_NAME_JS(name_substr: str, value: str) -> str:
    return (
        "(() => {"
        f" const needle = {json.dumps(name_substr.lower())};"
        " const el = [...document.querySelectorAll('input[type=text]')].find(i =>"
        "   (i.name || i.id || i.placeholder || '').toLowerCase().includes(needle));"
        " if (!el) return false;"
        " const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set;"
        f" setter.call(el, {json.dumps(value)});"
        " el.dispatchEvent(new Event('input', {bubbles: true}));"
        " el.dispatchEvent(new Event('change', {bubbles: true}));"
        " return true;"
        "})()"
    )


def _SET_REACT_TEXTAREA_BY_NAME_JS(name_substr: str, value: str) -> str:
    return (
        "(() => {"
        f" const needle = {json.dumps(name_substr.lower())};"
        " const el = [...document.querySelectorAll('textarea')].find(t =>"
        "   (t.name || t.id || t.placeholder || '').toLowerCase().includes(needle));"
        " if (!el) return false;"
        " const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value').set;"
        f" setter.call(el, {json.dumps(value)});"
        " el.dispatchEvent(new Event('input', {bubbles: true}));"
        " el.dispatchEvent(new Event('change', {bubbles: true}));"
        " return true;"
        "})()"
    )


def _SET_REACT_TEXTAREA_BY_PLACEHOLDER_JS(placeholder_substr: str, value: str) -> str:
    return _SET_REACT_TEXTAREA_BY_NAME_JS(placeholder_substr, value)


def _SET_DESCRIPTION_BBCODE_JS(bbcode: str) -> str:
    """Drive the SCEditor BBCode-mode editor.

    SCEditor stores the WYSIWYG HTML in an iframe and the BBCode equivalent
    in a hidden textarea. To make the React form's dirty tracker fire,
    write the BBCode through the editor instance's API: setSourceEditorValue
    -> updateOriginal. This propagates the value to the underlying textarea
    AND emits the `valuechanged` event the form listens for.
    """
    return (
        "(() => {"
        f" const bbcode = {json.dumps(bbcode)};"
        " // Find an SCEditor instance — it's stored on the textarea element."
        " const ta = [...document.querySelectorAll('textarea')].find(t => t._sceditor || t.bbcodeEditor || (t.parentElement && t.parentElement.classList && t.parentElement.classList.contains('bbcode-editor')));"
        " if (ta && ta._sceditor) {"
        "   const inst = ta._sceditor;"
        "   if (inst.sourceMode && !inst.sourceMode()) inst.toggleSourceMode && inst.toggleSourceMode();"
        "   inst.setSourceEditorValue ? inst.setSourceEditorValue(bbcode) : inst.val(bbcode);"
        "   if (inst.toggleSourceMode) inst.toggleSourceMode();"
        "   inst.updateOriginal && inst.updateOriginal();"
        "   ta.dispatchEvent(new Event('input', {bubbles: true}));"
        "   ta.dispatchEvent(new Event('change', {bubbles: true}));"
        "   return 'sceditor';"
        " }"
        " // Fallback: just write to the largest empty textarea."
        " const empty = [...document.querySelectorAll('textarea')].sort((a,b) => (b.clientHeight||0)-(a.clientHeight||0));"
        " if (empty.length) {"
        "   const t = empty[0];"
        "   const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(t), 'value').set;"
        "   setter.call(t, bbcode);"
        "   t.dispatchEvent(new Event('input', {bubbles: true}));"
        "   t.dispatchEvent(new Event('change', {bubbles: true}));"
        "   return 'fallback';"
        " }"
        " return 'no-editor';"
        "})()"
    )
