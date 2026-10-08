#!/usr/bin/env python3
"""Fetch one pinned public reference schema. Never fetch from XML schemaLocation."""
import hashlib
import json
from pathlib import Path
import urllib.request

REVISION = "ca1efa3cb23d35eef80f31d87ca189de44eb99fd"
FILE = "C2SIM_SMX_LOX_V1.0.1.xsd"
DIGEST = "33b02101c7144926514cbc244ffed0e34a842c8609e840ab6bf90e27c838e537"
URL = f"https://raw.githubusercontent.com/OpenC2SIM/OpenC2SIM.github.io/{REVISION}/{FILE}"
root = Path(__file__).resolve().parents[1] / ".cache/schemas/c2sim"
root.mkdir(parents=True, exist_ok=True)
data = urllib.request.urlopen(URL, timeout=30).read(4194305)
if hashlib.sha256(data).hexdigest() != DIGEST:
    raise SystemExit("Refusing reference schema digest mismatch")
(root / FILE).write_bytes(data)
manifest = {"version": "OpenC2SIM-SMX-LOX-1.0.1", "entry": FILE,
            "files": {FILE: DIGEST}, "root": "{http://www.sisostds.org/schemas/C2SIM/1.1}MessageBody"}
(root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
print(root / "manifest.json")
