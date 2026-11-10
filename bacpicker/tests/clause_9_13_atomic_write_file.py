# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.13 AtomicWriteFile Service Execution Tests."""

from __future__ import annotations

from ._common import register_manual

SERVICE = ["atomic-write-file"]
_IMAGE = "writes a file and checks it against the manufacturer's known image, which the tester does not have"

for _clause, _title in (
    ("9.13.1.1", "Writing to Record-Based Files"),
    ("9.13.1.2", "Writing to Stream-Based Files"),
    ("9.13.2.1", "Writing to Record Access Files"),
    ("9.13.2.2", "Writing to Stream Access Files"),
):
    register_manual(_clause, _title, _IMAGE, services=SERVICE, writes=True)
