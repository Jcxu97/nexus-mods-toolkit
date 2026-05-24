"""nexus_mods_toolkit — Drive nexusmods.com end-to-end from Python.

Three pillars:
- :func:`upload_mod` create a draft, fill the 5-step wizard, publish.
- :func:`add_new_file_version` push a new file to an existing mod page.
- :func:`download_mod` pull a .pak/.zip from a mod via the slow-download flow.

All three reuse the same browser-harness session (your real Chrome with your
Nexus login cookie). No API key required for upload/update; download uses an
API key only to resolve `mod_id -> file_id`, the file bytes still come from
Nexus's signed CDN URL.

Quickstart::

    from nexus_mods_toolkit import upload_mod, ModSpec
    spec = ModSpec(
        name="My Mod",
        author="MyHandle",
        version="1.0",
        category="Gameplay",
        short_description="A short description (under 512 chars).",
        description_bbcode=open("nexus_description.bbcode").read(),
        tags=("Bug Fixes", "Quality of Life"),
        header_image="header.png",
        gallery_images=["screenshot1.png"],
        files=[FileSpec(path="MyMod-v1.0.zip", version="1.0.0.0",
                        display_name="My Mod v1.0", category="Main")],
    )
    mod_url = upload_mod(spec)
    print(mod_url)  # https://www.nexusmods.com/baldursgate3/mods/<id>?published=1
"""
from __future__ import annotations

from .download import download_mod
from .update import add_new_file_version
from .upload import (
    FileSpec,
    ModSpec,
    create_draft,
    fill_general,
    publish,
    upload_file,
    upload_image,
    upload_mod,
)

__all__ = [
    "FileSpec",
    "ModSpec",
    "add_new_file_version",
    "create_draft",
    "download_mod",
    "fill_general",
    "publish",
    "upload_file",
    "upload_image",
    "upload_mod",
]

__version__ = "0.1.0"
