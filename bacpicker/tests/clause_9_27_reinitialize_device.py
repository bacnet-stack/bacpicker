# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.27 ReinitializeDevice Service Execution Tests."""

from __future__ import annotations

from ._common import register_manual

SERVICE = ["reinitialize-device"]
_REBOOT = (
    "restarts the IUT; the tester has no vendor password and does not rediscover the device after it reboots"
)
_PASSWORD = (
    "the tester does not know whether a password is required; omitting it can reboot an IUT that has none"
)

for _clause, _title, _reason in (
    ("9.27.1.1", "COLDSTART with no Password", _REBOOT),
    ("9.27.1.2", "COLDSTART with a Correct Password", _REBOOT),
    ("9.27.1.3", "WARMSTART with no Password", _REBOOT),
    ("9.27.1.4", "WARMSTART with a Correct Password", _REBOOT),
    ("9.27.2.3", "COLDSTART with Missing Password", _PASSWORD),
    ("9.27.2.4", "WARMSTART with Missing Password", _PASSWORD),
    ("9.27.2.5", "Rejects Unsupported Reinitialize Types",
        "requires the vendor's set of unsupported reinitialize types and a valid password"),
):
    register_manual(_clause, _title, _reason, services=SERVICE, writes=True)
