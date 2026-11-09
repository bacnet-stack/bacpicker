# Copyright 2026 Steve Karg <skarg@users.sourceforge.net>
# SPDX-License-Identifier: Apache-2.0

"""135.1-2023 9.3 UnconfirmedCOVNotification Service Execution Tests."""

from __future__ import annotations

from ._common import register_manual

_SERVICE = ["unconfirmed-cov-notification"]
_SUBSCRIBE = (
    "the IUT must subscribe to the TD; the tester is not a COV source the IUT is configured to monitor"
)

register_manual(
    "9.3.1",
    "Device Restart Notifications",
    "requires the IUT to restart and send an unsubscribed COV notification for the Device object",
    services=_SERVICE,
)
for _clause, _title in (
    ("9.3.2.1", "Change of Value Notifications"),
    ("9.3.2.2", "Change of Value Notification from Loop Objects"),
    ("9.3.2.3", "Change of Value Notification from Pulse Converter Object"),
    ("9.3.2.4", "Change of Value Notification from Load Control Object"),
    ("9.3.2.5", "UnconfirmedCOVNotification from Access Door Object"),
    ("9.3.2.6", "UnconfirmedCOVNotification from Access Point Object"),
    ("9.3.2.7", "UnconfirmedCOVNotification from Credential Data Input Object"),
):
    register_manual(_clause, _title, _SUBSCRIBE, services=_SERVICE)
