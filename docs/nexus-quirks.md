# Nexus quirks — the field manual

Notes on Nexus's edit UI that this library has had to work around. If a
field doesn't take, this is where to look first.

## Mod name character set

Nexus only accepts `letters + digits + spaces + _'().-` in the mod name
field. A `+`, `&`, `@`, `/`, or `:` will be silently rejected — the field
gets `aria-invalid="true"` and an error appears as a sibling element. If
your mod is `My Mod +2 ASI`, rename to `My Mod Plus 2 ASI`.

`upload.py:_validate_mod_name` raises a `ValueError` upfront so you don't
end up with a half-created draft.

## Description editor — SCEditor BBCode mode

The Full description field looks like a textarea, but it's an SCEditor
WYSIWYG instance with the BBCode source mirrored into a hidden textarea.
Writing directly to the textarea (with React's prototype `value` setter)
gets blown away on the next render — the WYSIWYG side is the
source of truth.

The library writes via the SCEditor instance API:

```js
inst.setSourceEditorValue(bbcode)   // pushes BBCode into source editor
inst.toggleSourceMode()              // forces sync to WYSIWYG
inst.updateOriginal()                // re-mirrors to the textarea
```

This emits the `valuechanged` event the React form's dirty tracker
listens for, so the Save button enables.

## Two Save buttons on the General tab

The page has a sticky Save at the top right (`idx 0`) and a footer Save
(`idx 1`). The sticky one stays disabled until React's dirty tracker
fires. The footer one updates state independently. Always click `idx 1`.

## Headless UI Combobox dynamic IDs

The category picker is a Headless UI `Combobox` whose option IDs
(`headlessui-combobox-input-_r_xxx_`) regenerate on every render. Don't
target by ID — locate by the `placeholder` or `aria-label`.

When picking an option, fire `mousedown` + `mouseup` + `click` on the
option. A bare `click` is sometimes ignored.

## Tags must come from the Popular Tags section

The tag input has a search box, but the search filter is so strict that
common keywords (e.g. `Quality of Life`) silently fail to match. Click
the chip directly in the **Popular tags** section at the bottom of the
General tab. The library does this — your job is to spell the chip
correctly:

```
Performance Optimization, Gameplay, Bug Fixes, Quality of Life,
Character Preset, AI-Generated Content, Animation - New, Textures,
User Interface, Translation, Utilities for Players
```

## File uploads — base64 + DataTransfer (not setFileInputFiles)

CDP's `DOM.setFileInputFiles` doesn't work on the Files tab — Nexus
re-mounts the React-controlled file input as soon as it sees the value,
clearing your file. The library uses the JS-side path:

```js
const file = new File([bytes], 'name.zip', {type: 'application/zip'});
const dt = new DataTransfer();
dt.items.add(file);
input.files = dt.files;
input.dispatchEvent(new Event('change', {bubbles: true}));
```

`input.files.length === 0` after the dispatch does **not** mean the
upload failed — React clears the list immediately. Verify by waiting
for the staged form (`#display-name` / `#file-version`) to appear.

## File version: don't use `1`

Nexus auto-fills the version field from the filename, often as just `1`.
This breaks Vortex's update detection (it expects `MAJOR.MINOR.PATCH.BUILD`).
Always overwrite to a 4-octet version like `1.0.0.0`.

## Header image opens a crop dialog

Dropping a file into the Header input opens a modal titled
`Adding header`. Click `Confirm`. The library waits for the modal then
clicks Confirm automatically.

## Publish is a double confirmation

The green Publish button at the top right opens a dialog. The dialog has
its own blue `Publish mod` button that does the actual publish. Clicking
only the first one leaves the mod in draft state forever.

Verification: after the second click, the URL must contain
`?published=1`, and a celebratory toast reads "Great job! Your mod is
live." If you don't see one of these, the publish silently failed.

## Step navigator markings

The 5-step navigator at the top of the edit pages shows asterisks for
incomplete required steps:

| Label                       | Meaning              |
|-----------------------------|----------------------|
| `1General *`                | Required, incomplete |
| `General` (no `*`)          | Required, complete   |
| `4RequirementsOptional`     | Optional, untouched  |
| `5PermissionsOptional`      | Optional, untouched  |

If the Publish button is grey, at least one `*` step is still pending.

## Update existing — the duplicate-entry bug

Nexus's "Update existing" picker can show two identical option rows when
the backend has produced duplicate file entries (an old bug, observed
2026-05-19 on mod 22964). React's selection logic then refuses to commit
because the choice is ambiguous — clicks, keystrokes, and dispatched
events all silently fail.

Workaround: switch to **Add as new file** (the radio group above the
picker). The new file lands at the top of the public Files list anyway
because Nexus orders by upload date desc. This is the path the library
takes in `update.add_new_file_version`.
