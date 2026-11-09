# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.12 AtomicReadFile Service Execution Tests.

The procedures compare the response with a file image supplied by the manufacturer.
That image is not available to the tester.
"""

from __future__ import annotations

from ._common import register_manual

SERVICE = ["atomic-read-file"]
_IMAGE = "requires the manufacturer's known file image (at least four records or four octets)"

for _clause, _title in (
    ("9.12.1.1", "Reading Record Based Files"),
    ("9.12.1.2", "Reading Stream Based Files"),
    ("9.12.2.1", "Reading Record Based Files"),
    ("9.12.2.2", "Reading Stream Based Files"),
):
    register_manual(_clause, _title, _IMAGE, services=SERVICE)
