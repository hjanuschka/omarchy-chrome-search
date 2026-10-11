#!/usr/bin/env python3
"""Register the native host for a locally loaded Chromium extension."""

import json
from pathlib import Path
import re
import sys

if len(sys.argv) != 2 or not re.fullmatch(r"[a-p]{32}", sys.argv[1]):
    sys.exit("Usage: python3 bridge/install.py <extension ID from chrome://extensions>")

repo = Path(__file__).resolve().parent.parent
plugin = Path.home() / ".config/omarchy/plugins/hjanuschka.chrome-search"
if plugin.is_symlink() and plugin.resolve() != repo / "omarchy-plugin":
    sys.exit(f"Plugin path belongs to a different installation: {plugin}")
if plugin.exists() and not plugin.is_symlink():
    sys.exit(f"Plugin path already exists: {plugin}")

host = repo / "bridge" / "bridge.py"
host.chmod(0o755)
manifest = {
    "name": "com.hjanuschka.omarchy_chrome_search",
    "description": "Local Omarchy Chrome Search bridge",
    "path": str(host),
    "type": "stdio",
    "allowed_origins": [f"chrome-extension://{sys.argv[1]}/"],
}
for browser in ("chromium", "google-chrome"):
    directory = Path.home() / ".config" / browser / "NativeMessagingHosts"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (manifest["name"] + ".json")
    target.write_text(json.dumps(manifest, indent=2) + "\n")
    print(target)

if not plugin.is_symlink():
    plugin.parent.mkdir(parents=True, exist_ok=True)
    plugin.symlink_to(repo / "omarchy-plugin", target_is_directory=True)
    print(plugin)

launcher = Path.home() / ".local/bin/omarchy-chrome-search"
launcher.parent.mkdir(parents=True, exist_ok=True)
launcher.write_text(f'#!/bin/sh\nexec python3 "{host}" "$@"\n')
launcher.chmod(0o755)
print(launcher)
print("Run: omarchy-shell shell rescanPlugins && omarchy plugin enable hjanuschka.chrome-search")
