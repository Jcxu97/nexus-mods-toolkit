"""Upload a brand-new mod to nexusmods.com from a local folder.

Pre-flight:
  1. Log in to https://www.nexusmods.com in the Chrome that browser-harness
     drives. The session cookie is the only auth this script uses.
  2. Have a built .zip ready (e.g. an LSPK pak + info.json zipped together).

Usage:
  python upload_new_mod.py
"""
from pathlib import Path

from nexus_mods_toolkit import FileSpec, ModSpec, upload_mod

# Where you keep the build artefacts on disk.
HERE = Path(__file__).parent

description_bbcode = """[size=4][b]My Awesome Mod[/b][/size]

A short description of what the mod does, who it's for, and why someone
should download it. 1-3 sentences for the hook, then bullet features.

[size=3][b]What it changes[/b][/size]

[list]
[*]Adds X.
[*]Restores Y.
[/list]

[size=3][b]Hard dependencies[/b][/size]

[list]
[*][b]Other Mod Name[/b] — REQUIRED. Reason it's required.
[/list]

[size=3][b]Installation[/b][/size]

[list=1]
[*]Drop the zip into BG3MM.
[*]Make sure load order is …
[*]Launch the game.
[/list]
"""

spec = ModSpec(
    name="My Awesome Mod",
    author="MyHandle",
    version="1.0",
    category="Gameplay",
    short_description="A short description (under 512 chars) shown on the mod card.",
    description_bbcode=description_bbcode,
    tags=("Bug Fixes", "Quality of Life"),
    header_image=HERE / "header.png",       # optional but very recommended
    gallery_images=[HERE / "screenshot.png"],  # at least one required
    files=[
        FileSpec(
            path=HERE / "MyMod-v1.0.zip",
            version="1.0.0.0",
            display_name="My Awesome Mod v1.0",
            category="Main",
        ),
    ],
)

if __name__ == "__main__":
    url = upload_mod(spec)
    print("Live:", url)
