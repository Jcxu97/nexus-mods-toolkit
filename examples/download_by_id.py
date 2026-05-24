"""Download a mod's main file by its mod id.

Pre-flight:
  1. Log in to https://www.nexusmods.com in the Chrome that browser-harness
     drives.
  2. Set NEXUS_API_KEY env var (or write it to %USERPROFILE%/.nexus-api-key)
     so we can resolve "latest main file" via the public API. Get a key at:
       https://www.nexusmods.com/users/myaccount?tab=api%20access

Usage:
  python download_by_id.py 23045
"""
import sys
from pathlib import Path

from nexus_mods_toolkit import download_mod

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    mod_id = int(sys.argv[1])
    out = download_mod(mod_id, dest_dir=Path("./downloads"))
    print(f"Downloaded -> {out}")
