"""Push a new file version to an existing Nexus mod page.

Pre-flight:
  1. Log in to https://www.nexusmods.com in the Chrome that browser-harness
     drives. You must be the author (or part of the author team) of the
     target mod, otherwise the Files tab won't render the upload UI.

Usage:
  python push_update.py
"""
from pathlib import Path

from nexus_mods_toolkit import add_new_file_version

if __name__ == "__main__":
    add_new_file_version(
        mod_id=23045,
        file_path=Path("./MyMod-v1.1.zip"),
        version="1.1.0.0",
        display_name="My Awesome Mod v1.1",
        changelog=(
            "v1.1\n"
            "- Fixed X.\n"
            "- Added Y.\n"
        ),
        category="Main",
    )
    print("Update pushed. Verify on the mod's Files tab.")
