# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""Extract the Annex K BIBB service tables from the 135 markdown into bacpicker/data/bibbs.json.

Usage: python tools/extract_bibbs.py /path/to/ASHRAE-135.md
Object type requirements are prose in Annex K and are curated in bacpicker/bibbs.py.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HEADING = re.compile(r"(K\.\d+\.\d+)\s+BIBB\s+-\s+([^()]*?)\s*\(([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\)")
ROW = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|")
OUT = Path(__file__).resolve().parent.parent / "bacpicker" / "data" / "bibbs.json"


def application_services() -> dict:
    """Normalized name -> Protocol_Services_Supported bit name, e.g. 'readproperty' -> 'read-property'."""
    sys.path.insert(0, str(OUT.parent.parent.parent))
    from bacpicker.standard import normalize, service_bits

    return {normalize(n): n for n in service_bits()}


def mark(cell: str) -> str:
    """'' = not required, 'x' = required, 'conditional' = x with a footnote."""
    if not cell.lower().startswith("x"):
        return ""
    return "conditional" if "<sup>" in cell else "x"


def extract(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, line in enumerate(lines) if "ANNEX K - BACnet INTEROPERABILITY BUILDING BLOCKS" in line
    )
    end = next(i for i, line in enumerate(lines) if i > start and line.startswith("#### ANNEX L"))
    bibbs: dict = {}
    services = application_services()
    current = None
    for line in lines[start:end]:
        # the heading regex is slow on the long table/prose lines, so pre-filter
        for clause, title, acronym in HEADING.findall(line) if "BIBB" in line else ():
            current = bibbs.setdefault(acronym, {"clause": clause, "title": title, "services": {}})
        row = ROW.match(line.strip())
        if current is None or not row:
            continue
        service, initiate, execute = row.groups()
        # only application services are recorded (not BVLL / network layer messages)
        bit_name = services.get(re.sub(r"[^a-z]", "", service.lower()))
        if bit_name is None:
            continue
        current["services"][bit_name] = {"initiate": mark(initiate), "execute": mark(execute)}
    return bibbs


def main() -> None:
    bibbs = extract(Path(sys.argv[1]))
    OUT.write_text(json.dumps(bibbs, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(bibbs)} BIBBs written to {OUT}")


if __name__ == "__main__":
    main()
