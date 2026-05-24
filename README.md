# nexus-mods-toolkit

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Built on browser-harness](https://img.shields.io/badge/built%20on-browser--harness-orange.svg)](https://github.com/Jcxu97/browser-harness)
[![Tested on BG3](https://img.shields.io/badge/tested%20on-Baldur's%20Gate%203-purple.svg)](https://www.nexusmods.com/baldursgate3)

> Drive [nexusmods.com](https://www.nexusmods.com) end-to-end from Python.
> Upload mods, push updates, download files — all from your real Chrome,
> using the cookies you already have.

A small Python library that automates the three things modders do over and
over on Nexus: **publish a new mod**, **push an update**, **pull a file**.
Built on [browser-harness](https://github.com/Jcxu97/browser-harness) so
the browser stays headed and visible — no headless Puppeteer / Playwright
fingerprint, no API key required for upload, and no fighting Cloudflare.

---

## Why this exists

Nexus's edit UI has 11+ unwritten quirks that make the obvious approaches
fail silently. A few examples:

- The mod name field rejects `+`, `&`, `@`, `/`, `:` — but only with an
  invisible `aria-invalid` attribute, no popup.
- The description "textarea" is actually an SCEditor WYSIWYG instance
  with a BBCode mirror — writing directly to the textarea silently fails.
- File uploads via `DOM.setFileInputFiles` get cleared on re-render — you
  have to go through `DataTransfer` from JS.
- "Publish" is a *double* confirmation — first the page-level button,
  then a `Publish mod` button inside the dialog. Click only the first
  and your mod stays in draft state forever.
- Update existing has a backend bug that produces duplicate file entries
  on the second update; React's selection refuses to commit.

This library encodes the workarounds for all of them. See
[`docs/nexus-quirks.md`](docs/nexus-quirks.md) for the full list.

---

## Install

```bash
pip install git+https://github.com/Jcxu97/nexus-mods-toolkit.git
```

This pulls [browser-harness](https://github.com/Jcxu97/browser-harness)
as a dependency. browser-harness drives a real Chrome via the Chrome
DevTools Protocol — see its README for one-time setup (start Chrome with
`--remote-debugging-port=9222` etc.).

Pre-flight, once:

1. Open https://www.nexusmods.com in the Chrome that browser-harness
   drives, and **log in**. The session cookie is the only auth this
   library uses for upload/update.
2. (Download only) Generate a personal Nexus API key from
   [your account settings](https://www.nexusmods.com/users/myaccount?tab=api%20access)
   and either set `NEXUS_API_KEY` env var or save it to
   `%USERPROFILE%/.nexus-api-key`.

---

## Quickstart

### Upload a brand-new mod

```python
from pathlib import Path
from nexus_mods_toolkit import FileSpec, ModSpec, upload_mod

spec = ModSpec(
    name="My Awesome Mod",
    author="MyHandle",
    version="1.0",
    category="Gameplay",
    short_description="A short description (under 512 chars).",
    description_bbcode=Path("description.bbcode").read_text(),
    tags=("Bug Fixes", "Quality of Life"),
    header_image="header.png",
    gallery_images=["screenshot.png"],
    files=[
        FileSpec(
            path="MyMod-v1.0.zip",
            version="1.0.0.0",
            display_name="My Awesome Mod v1.0",
            category="Main",
        ),
    ],
)

url = upload_mod(spec)
print(url)  # https://www.nexusmods.com/baldursgate3/mods/<id>?published=1
```

### Push an update to an existing mod

```python
from nexus_mods_toolkit import add_new_file_version

add_new_file_version(
    mod_id=23045,
    file_path="MyMod-v1.1.zip",
    version="1.1.0.0",
    display_name="My Awesome Mod v1.1",
    changelog="v1.1\n- Fixed X.\n- Added Y.\n",
)
```

### Download a mod by id

```python
from nexus_mods_toolkit import download_mod

path = download_mod(23045, dest_dir="./downloads")
print(f"Downloaded -> {path}")
```

More runnable scripts in [`examples/`](examples/).

---

## How it works

Every action goes through one shared agent tab inside the user's **second
Chrome window**. The library never steals focus from the active tab in
the main window; you can keep working while a mod uploads in the
background.

For upload / update, the library:

1. Opens the upload modal (`Upload` → `Upload mod` — both `<button>`,
   not `<a>`).
2. Fills the 4-field draft modal and clicks `Create draft`. Nexus
   redirects to `/mods/<NEW_ID>/edit/general`.
3. Walks the 5-step wizard (General → Media → Files → Requirements →
   Permissions). Each step has its own quirks; see `docs/nexus-quirks.md`.
4. Clicks the green `Publish` button at the top right, then `Publish
   mod` in the confirmation dialog.
5. Verifies the URL contains `?published=1` before reporting success.

For download, the library:

1. Resolves `mod_id → file_id` via Nexus's public REST API (free-tier
   compatible — the API call itself doesn't require Premium).
2. Opens the mod's Files tab in the agent tab and clicks `Slow download`.
3. Captures the signed CDN URL via `Page.downloadWillBegin` over CDP.
4. Fetches the URL with stdlib `urllib`. The signed URL is
   self-authenticating, so no cookies / headers / proxies are needed.

---

## Tested games

Validated end-to-end on:

- ✅ **Baldur's Gate 3** ([baldursgate3](https://www.nexusmods.com/baldursgate3))
  — first publish flow, file updates, and downloads all confirmed.

The 5-step wizard is shared across every Nexus game, so Skyrim / Fallout
4 / Cyberpunk / etc. should work with no code changes — pass the game
slug as the `game=` keyword argument. Reports of breakages welcome via
[issues](https://github.com/Jcxu97/nexus-mods-toolkit/issues).

---

## Project layout

```
nexus-mods-toolkit/
├── src/nexus_mods_toolkit/
│   ├── __init__.py     # Public API
│   ├── upload.py       # Create draft + 5-step wizard + publish
│   ├── update.py       # Push a new file as a brand-new entry
│   ├── download.py     # Slow-download capture + urllib fetch
│   └── _browser.py     # browser-harness session helpers
├── examples/           # Runnable scripts
├── docs/
│   └── nexus-quirks.md # The full field manual
├── pyproject.toml
└── LICENSE
```

---

## FAQ

**Why not the official Nexus REST API?**
The REST API's download endpoint requires a **Premium** subscription. For
free-tier users the only path to a mod's bytes is the Slow-download
button, which this library automates. The upload / update endpoints
(`/v1/games/.../mods/.../upload`) aren't documented and don't seem to
exist for non-Premium users either.

**Why a real Chrome instead of Playwright headless?**
Two reasons. First, your Nexus login already lives in your normal Chrome —
browser-harness reuses it, no scripting of OAuth flows. Second, Nexus's
edit pages use Cloudflare's bot challenge in a way that triggers
infrequently for headed Chrome but reliably for headless Playwright /
Puppeteer.

**Can I run two upload tasks in parallel?**
Not against the same Nexus session — Nexus issues per-session CSRF
tokens that don't survive concurrent edits. browser-harness *can* drive
multiple agent tabs in one window, but you'd be racing the same cookies.

**Will it work on macOS / Linux?**
The library itself is platform-independent, but browser-harness
currently supports Windows + macOS only (Linux Chrome's CDP is fine,
but the agent-tab management uses Win32 / AppKit window APIs).

---

## Contributing

This is a small library focused on staying small. Bug reports for things
that broke (especially game-specific UI changes) are very welcome. Big
features should probably live in their own repo.

Run the linter before sending a PR:

```bash
pip install -e ".[dev]"
ruff check src/
```

---

## Credits

- [browser-harness](https://github.com/Jcxu97/browser-harness) — the
  Chrome / CDP layer this library is built on.
- The 11 quirks in `docs/nexus-quirks.md` were paid for in human time
  by everyone who's ever stared at a silently-failing Nexus form.

---

## License

MIT — see [LICENSE](LICENSE).
