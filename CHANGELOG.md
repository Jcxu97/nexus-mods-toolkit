# Changelog

## 0.1.0 — 2026-05-24

Initial release. Extracted from inline browser-harness work after publishing
[REL Ancient AMP Mix](https://www.nexusmods.com/baldursgate3/mods/23045)
end-to-end via automation.

### Features

- `upload_mod(spec)` — full create-draft + 5-step wizard + publish flow.
- `add_new_file_version(...)` — push a new file to an existing mod via the
  Add-as-new-file path (sidesteps the Update-existing duplicate bug).
- `download_mod(mod_id, ...)` — slow-download capture for free-tier accounts.
- `docs/nexus-quirks.md` — the full field manual of UI workarounds.

### Tested

- Baldur's Gate 3 mod 23045 (REL Ancient AMP Mix v1.0): create draft,
  fill General + Media + Files, publish to live.
